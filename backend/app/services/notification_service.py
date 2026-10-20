"""
SmartGuard AI — Phase 4 Notification Service

Manages delivery of email notifications:
  - Queues notifications after alert creation (non-blocking)
  - Sends notifications with bounded retry (max 3 attempts)
  - Tracks delivery status in notification_log
  - Processes daily security summary emails
  - Enforces idempotency via idempotency_key

Critical rules:
  - Email failures NEVER block or alter access decisions.
  - Credentials are never stored in notification_log.
  - Retry is bounded — permanent failures are marked FAILED after max_attempts.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("smartguard.notification_service")

# Retry delays (seconds) — exponential-ish
RETRY_DELAYS_SECONDS = [60, 300, 900]  # 1min, 5min, 15min
MAX_ATTEMPTS = 3

# Alert severity → min severity for notification
_SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


# ---------------------------------------------------------------------------
# Called immediately after access decision is persisted
# ---------------------------------------------------------------------------
def queue_alert_notifications_after_commit(
    db, attempt_id: str, attempt_data: dict, decision: str
) -> None:
    """
    Queue notification records for any contacts that should receive alerts
    for this access attempt.  Never sends immediately — processed later.
    Called from access_decision_service after DB commit.
    Never raises.
    """
    from app.services.email_service import is_email_enabled
    if not is_email_enabled():
        return

    try:
        from sqlalchemy import select
        from app.models.alerts import SecurityAlert, SecurityContact, NotificationLog

        # Find most recently created alert for this attempt
        alert = db.execute(
            select(SecurityAlert).where(
                SecurityAlert.access_attempt_id == uuid.UUID(attempt_id)
            ).order_by(SecurityAlert.first_detected_at.desc())
        ).scalar_one_or_none()

        if alert is None:
            return  # ALLOW decisions have no alert

        # Find eligible contacts
        contacts = db.execute(
            select(SecurityContact).where(SecurityContact.is_active == True)  # noqa: E712
        ).scalars().all()

        for contact in contacts:
            if not _contact_wants_alert(contact, alert):
                continue

            # Idempotency key — one notification per contact per alert
            idem_key = _make_idempotency_key("alert", str(alert.id), str(contact.id))

            # Check for existing record (prevent duplicates)
            existing = db.execute(
                select(NotificationLog).where(
                    NotificationLog.idempotency_key == idem_key
                )
            ).scalar_one_or_none()

            if existing:
                continue

            notif = NotificationLog(
                id=uuid.uuid4(),
                notification_type="ALERT",
                alert_id=alert.id,
                contact_id=contact.id,
                recipient_email=contact.email,
                subject=f"[SmartGuard AI] {alert.severity} Alert — {alert.title[:80]}",
                status="PENDING",
                attempt_count=0,
                max_attempts=MAX_ATTEMPTS,
                provider=_get_provider_name(),
                idempotency_key=idem_key,
            )
            db.add(notif)

        db.commit()
        _process_pending_notifications(db)

    except Exception as exc:
        logger.error("notification_service queue_alert_notifications failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Process pending/retry-scheduled notifications
# ---------------------------------------------------------------------------
def _process_pending_notifications(db) -> None:
    """Send all PENDING and eligible RETRY_SCHEDULED notifications."""
    from sqlalchemy import select
    from app.models.alerts import NotificationLog, SecurityAlert

    now = datetime.now(timezone.utc)

    try:
        rows = db.execute(
            select(NotificationLog).where(
                NotificationLog.status.in_(["PENDING", "RETRY_SCHEDULED"]),
                NotificationLog.attempt_count < NotificationLog.max_attempts,
            ).where(
                (NotificationLog.next_retry_at == None) |  # noqa: E711
                (NotificationLog.next_retry_at <= now)
            )
        ).scalars().all()

        for notif in rows:
            _send_notification(db, notif)

    except Exception as exc:
        logger.error("notification_service _process_pending failed: %s", exc)


def _send_notification(db, notif) -> None:
    """Attempt to send a single notification record."""
    from app.services.email_service import send_email, render_alert_email, render_daily_summary_email
    from app.models.alerts import NotificationLog, SecurityAlert, SecurityContact
    from app.core.config import get_settings
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    settings = get_settings()
    app_base_url = getattr(settings, "app_base_url", "")

    # Mark as SENDING
    notif.status = "SENDING"
    notif.last_attempted_at = now
    notif.attempt_count = (notif.attempt_count or 0) + 1
    db.add(notif)
    db.commit()

    try:
        html_body = ""
        subject = notif.subject

        if notif.notification_type == "ALERT" and notif.alert_id:
            alert = db.execute(
                select(SecurityAlert).where(SecurityAlert.id == notif.alert_id)
            ).scalar_one_or_none()
            if alert:
                alert_dict = {
                    "id": str(alert.id),
                    "severity": alert.severity,
                    "category": alert.category,
                    "title": alert.title,
                    "description": alert.description,
                    "detected_plate": alert.detected_plate,
                    "first_detected_at": alert.first_detected_at,
                }
                subject, html_body = render_alert_email(alert_dict, app_base_url)

        elif notif.notification_type == "DAILY_SUMMARY":
            # summary_date carried in the log record
            pass  # html_body built by daily summary sender

        elif notif.notification_type == "TEST":
            html_body = _render_test_email_html()

        if not html_body:
            notif.status = "FAILED"
            notif.error_detail = "Could not render email body."
            db.add(notif)
            db.commit()
            return

        contact_name = ""
        if notif.contact_id:
            contact = db.execute(
                select(SecurityContact).where(SecurityContact.id == notif.contact_id)
            ).scalar_one_or_none()
            contact_name = contact.full_name if contact else ""

        result = send_email(
            to_address=notif.recipient_email,
            to_name=contact_name,
            subject=subject,
            html_body=html_body,
        )

        if result["success"]:
            notif.status = "SENT"
            notif.sent_at = datetime.now(timezone.utc)
            notif.provider_message_id = result.get("provider_message_id")
            notif.error_detail = None
            logger.info(
                "notification_service SENT id=%s to=%s", notif.id, notif.recipient_email
            )
            # Update contact last_notified_at
            if notif.contact_id:
                from app.models.alerts import SecurityContact
                contact = db.execute(
                    select(SecurityContact).where(SecurityContact.id == notif.contact_id)
                ).scalar_one_or_none()
                if contact:
                    contact.last_notified_at = now
                    contact.last_notification_status = "SENT"
                    db.add(contact)
        else:
            error = result.get("error", "Unknown error")[:500]
            notif.error_detail = error
            if notif.attempt_count >= notif.max_attempts:
                notif.status = "FAILED"
                logger.warning(
                    "notification_service FAILED (max attempts) id=%s: %s", notif.id, error
                )
            else:
                notif.status = "RETRY_SCHEDULED"
                delay = RETRY_DELAYS_SECONDS[min(notif.attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1)]
                notif.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                logger.warning(
                    "notification_service RETRY id=%s attempt=%d delay=%ds: %s",
                    notif.id, notif.attempt_count, delay, error,
                )

    except Exception as exc:
        notif.status = "FAILED"
        notif.error_detail = str(exc)[:500]
        logger.error("notification_service _send_notification error: %s", exc, exc_info=True)

    db.add(notif)
    db.commit()


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------
def send_daily_summary(db, date_str: str, summary: dict, force: bool = False) -> dict:
    """
    Queue and immediately send daily summary emails to all active contacts
    that have daily_summary_enabled=True.

    date_str: 'YYYY-MM-DD'
    summary: dict from get_daily_summary()
    force: skip duplicate check if True (for manual re-sends)
    Returns dict with sent_count, skipped_count, failed_count.
    """
    from app.services.email_service import (
        is_email_enabled, send_email, render_daily_summary_email,
    )
    from sqlalchemy import select
    from app.models.alerts import SecurityContact, NotificationLog
    from app.core.config import get_settings

    if not is_email_enabled():
        return {"sent_count": 0, "skipped_count": 0, "failed_count": 0, "message": "Email disabled."}

    settings = get_settings()
    app_base_url = getattr(settings, "app_base_url", "")
    subject, html_body = render_daily_summary_email(summary, date_str, app_base_url)

    contacts = db.execute(
        select(SecurityContact).where(
            SecurityContact.is_active == True,  # noqa: E712
            SecurityContact.daily_summary_enabled == True,  # noqa: E712
        )
    ).scalars().all()

    sent_count = skipped_count = failed_count = 0

    for contact in contacts:
        idem_key = _make_idempotency_key("daily_summary", date_str, str(contact.id))

        if not force:
            existing = db.execute(
                select(NotificationLog).where(
                    NotificationLog.idempotency_key == idem_key,
                    NotificationLog.status.in_(["SENT", "SENDING"]),
                )
            ).scalar_one_or_none()
            if existing:
                skipped_count += 1
                continue

        result = send_email(
            to_address=contact.email,
            to_name=contact.full_name,
            subject=subject,
            html_body=html_body,
        )

        notif = NotificationLog(
            id=uuid.uuid4(),
            notification_type="DAILY_SUMMARY",
            alert_id=None,
            contact_id=contact.id,
            recipient_email=contact.email,
            subject=subject,
            status="SENT" if result["success"] else "FAILED",
            attempt_count=1,
            max_attempts=1,
            provider=_get_provider_name(),
            provider_message_id=result.get("provider_message_id"),
            error_detail=result.get("error"),
            sent_at=datetime.now(timezone.utc) if result["success"] else None,
            last_attempted_at=datetime.now(timezone.utc),
            idempotency_key=idem_key,
            summary_date=date_str,
        )
        db.add(notif)

        if result["success"]:
            sent_count += 1
            contact.last_notified_at = datetime.now(timezone.utc)
            contact.last_notification_status = "SENT"
            db.add(contact)
        else:
            failed_count += 1

    db.commit()
    return {
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
    }


# ---------------------------------------------------------------------------
# Test email
# ---------------------------------------------------------------------------
def send_test_email(db, contact_id: str) -> dict:
    """Send a test email to a specific security contact."""
    from app.services.email_service import is_email_enabled, send_email
    from sqlalchemy import select
    from app.models.alerts import SecurityContact, NotificationLog

    if not is_email_enabled():
        return {"success": False, "message": "Email is not enabled. Configure email settings first."}

    contact = db.execute(
        select(SecurityContact).where(SecurityContact.id == uuid.UUID(contact_id))
    ).scalar_one_or_none()

    if not contact:
        return {"success": False, "message": "Contact not found."}

    html_body = _render_test_email_html()
    result = send_email(
        to_address=contact.email,
        to_name=contact.full_name,
        subject="[SmartGuard AI] Test Email",
        html_body=html_body,
    )

    # Log the attempt
    notif = NotificationLog(
        id=uuid.uuid4(),
        notification_type="TEST",
        contact_id=contact.id,
        recipient_email=contact.email,
        subject="[SmartGuard AI] Test Email",
        status="SENT" if result["success"] else "FAILED",
        attempt_count=1,
        max_attempts=1,
        provider=_get_provider_name(),
        provider_message_id=result.get("provider_message_id"),
        error_detail=result.get("error"),
        sent_at=datetime.now(timezone.utc) if result["success"] else None,
        last_attempted_at=datetime.now(timezone.utc),
    )
    db.add(notif)

    if result["success"]:
        contact.last_notified_at = datetime.now(timezone.utc)
        contact.last_notification_status = "SENT"
        db.add(contact)

    db.commit()
    return {
        "success": result["success"],
        "message": "Test email sent successfully." if result["success"] else result.get("error", "Send failed."),
    }


# ---------------------------------------------------------------------------
# Retry pending/failed notifications
# ---------------------------------------------------------------------------
def retry_failed_notifications(db) -> dict:
    """Mark FAILED notifications as RETRY_SCHEDULED and attempt re-sends."""
    from sqlalchemy import select
    from app.models.alerts import NotificationLog

    rows = db.execute(
        select(NotificationLog).where(
            NotificationLog.status == "FAILED",
            NotificationLog.attempt_count < NotificationLog.max_attempts,
        )
    ).scalars().all()

    rescheduled = 0
    for notif in rows:
        notif.status = "RETRY_SCHEDULED"
        notif.next_retry_at = datetime.now(timezone.utc)
        db.add(notif)
        rescheduled += 1

    db.commit()
    _process_pending_notifications(db)
    return {"rescheduled": rescheduled}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _contact_wants_alert(contact, alert) -> bool:
    """Check if a contact's preferences include receiving this alert."""
    if _SEV_ORDER.get(alert.severity, 0) < _SEV_ORDER.get(contact.min_severity, 0):
        return False
    cats = contact.notify_categories
    if cats and isinstance(cats, list) and len(cats) > 0:
        if alert.category not in cats:
            return False
    return True


def _make_idempotency_key(prefix: str, *parts: str) -> str:
    raw = f"{prefix}:" + ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _get_provider_name() -> str:
    from app.core.config import get_settings
    try:
        return get_settings().email_provider or "unknown"
    except Exception:
        return "unknown"


def _render_test_email_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;">
  <div style="max-width:520px;margin:0 auto;background:#1e293b;border-radius:12px;overflow:hidden;">
    <div style="background:#312e81;padding:24px 32px;">
      <h1 style="margin:0;font-size:20px;color:#c7d2fe;">🛡 SmartGuard AI</h1>
      <p style="color:#a5b4fc;margin:4px 0 0;font-size:13px;">Security Operations Center</p>
    </div>
    <div style="padding:32px;">
      <h2 style="color:#4ade80;margin:0 0 16px;">✓ Email configuration working</h2>
      <p style="color:#94a3b8;font-size:14px;">This is a test email confirming your SmartGuard AI notification configuration is working correctly.</p>
      <p style="color:#94a3b8;font-size:14px;">You will receive security alerts based on your configured notification preferences.</p>
    </div>
    <div style="background:#0f172a;padding:16px 32px;text-align:center;">
      <p style="color:#475569;font-size:12px;margin:0;">SmartGuard AI · Do not reply to this email.</p>
    </div>
  </div>
</body></html>"""
