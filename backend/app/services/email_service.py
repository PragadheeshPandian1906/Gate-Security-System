"""
SmartGuard AI — Phase 4 Email Service

Provides HTML email delivery via Brevo (formerly Sendinblue) transactional API
or optionally SMTP as a fallback.

Security rules:
  - API keys and SMTP credentials are NEVER returned to the frontend.
  - Credentials are read exclusively from Settings (environment variables).
  - This service MUST NOT block or raise in a way that disrupts access decisions.
  - Template rendering happens server-side only.

Free-tier limits (Brevo as of 2026):
  - 300 emails/day on the free plan.
  - Sender domain/address must be verified in the Brevo dashboard.
"""
import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger("smartguard.email_service")


# ---------------------------------------------------------------------------
# Settings-based configuration check
# ---------------------------------------------------------------------------
def is_email_enabled() -> bool:
    """Return True only if EMAIL_ENABLED=true and a provider is configured."""
    from app.core.config import get_settings
    s = get_settings()
    return s.email_enabled and bool(
        (s.email_provider == "brevo" and s.email_api_key) or
        (s.email_provider == "smtp" and s.smtp_host)
    )


def get_email_config_status() -> dict:
    """Return a safe (no secrets) summary of email configuration for the admin UI."""
    from app.core.config import get_settings
    s = get_settings()
    return {
        "email_enabled": s.email_enabled,
        "provider": s.email_provider,
        "from_address": s.email_from_address,
        "from_name": s.email_from_name,
        "api_key_configured": bool(s.email_api_key),
        "smtp_host_configured": bool(s.smtp_host),
    }


# ---------------------------------------------------------------------------
# Core send function — never raises, always returns a result dict
# ---------------------------------------------------------------------------
def send_email(
    to_address: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    attachments: Optional[list] = None,
) -> dict:
    """
    Send a single transactional email.

    Args:
        attachments: Optional list of dicts with keys:
            - name: str  (filename, e.g. "visitor_pass_qr.png")
            - content: str  (base64-encoded file content)
            - content_type: str  (MIME type, e.g. "image/png")

    Returns:
        dict with keys: success (bool), provider_message_id (str|None), error (str|None)
    """
    if not is_email_enabled():
        logger.info("email_service Email disabled — skipping send to %s", to_address)
        return {"success": False, "provider_message_id": None, "error": "Email is disabled."}

    from app.core.config import get_settings
    s = get_settings()

    try:
        if s.email_provider == "brevo":
            return _send_via_brevo(to_address, to_name, subject, html_body, text_body, s, attachments)
        elif s.email_provider == "smtp":
            return _send_via_smtp(to_address, to_name, subject, html_body, text_body, s, attachments)
        else:
            return {"success": False, "provider_message_id": None, "error": f"Unknown provider: {s.email_provider}"}
    except Exception as exc:
        logger.error("email_service Unexpected error sending to %s: %s", to_address, exc, exc_info=True)
        return {"success": False, "provider_message_id": None, "error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# Brevo transactional API
# ---------------------------------------------------------------------------
def _send_via_brevo(
    to_address: str, to_name: str, subject: str,
    html_body: str, text_body: Optional[str], settings,
    attachments: Optional[list] = None,
) -> dict:
    """Send via Brevo (Sendinblue) transactional email API v3."""
    try:
        import urllib.request
        import urllib.error
        import json

        payload = {
            "sender": {
                "name": settings.email_from_name,
                "email": settings.email_from_address,
            },
            "to": [{"email": to_address, "name": to_name}],
            "subject": subject,
            "htmlContent": html_body,
        }
        if text_body:
            payload["textContent"] = text_body

        # Brevo attachment format: [{"name": str, "content": base64_str}]
        if attachments:
            payload["attachment"] = [
                {
                    "name": att["name"],
                    "content": att["content"],  # already base64
                }
                for att in attachments
            ]

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=body_bytes,
            method="POST",
        )
        req.add_header("accept", "application/json")
        req.add_header("api-key", settings.email_api_key)
        req.add_header("content-type", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            message_id = resp_data.get("messageId") or resp_data.get("message_id")
            logger.info(
                "email_service Brevo accepted email to %s messageId=%s", to_address, message_id
            )
            return {"success": True, "provider_message_id": str(message_id or ""), "error": None}

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.error(
            "email_service Brevo HTTP error %s to %s: %s", exc.code, to_address, body
        )
        return {
            "success": False,
            "provider_message_id": None,
            "error": f"Brevo HTTP {exc.code}: {body[:200]}",
        }
    except Exception as exc:
        logger.error("email_service Brevo send failed to %s: %s", to_address, exc)
        return {"success": False, "provider_message_id": None, "error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# SMTP fallback
# ---------------------------------------------------------------------------
def _send_via_smtp(
    to_address: str, to_name: str, subject: str,
    html_body: str, text_body: Optional[str], settings,
    attachments: Optional[list] = None,
) -> dict:
    """Send via SMTP (e.g., Gmail App Password, Mailgun SMTP)."""
    import base64 as _b64
    from email.mime.application import MIMEApplication
    try:
        # Use 'mixed' if attachments present, else 'alternative'
        if attachments:
            outer = MIMEMultipart("mixed")
            outer["Subject"] = subject
            outer["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
            outer["To"] = f"{to_name} <{to_address}>"
            # Inner alternative part (text + html)
            alt = MIMEMultipart("alternative")
            if text_body:
                alt.attach(MIMEText(text_body, "plain", "utf-8"))
            alt.attach(MIMEText(html_body, "html", "utf-8"))
            outer.attach(alt)
            # Attach each file
            for att in attachments:
                raw_bytes = _b64.b64decode(att["content"])
                part = MIMEApplication(raw_bytes, Name=att["name"])
                part["Content-Disposition"] = f'attachment; filename="{att["name"]}"'
                outer.attach(part)
            msg = outer
        else:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
            msg["To"] = f"{to_name} <{to_address}>"
            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        port = settings.smtp_port
        use_tls = settings.smtp_use_tls

        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.sendmail(settings.email_from_address, [to_address], msg.as_string())
        else:
            with smtplib.SMTP_SSL(settings.smtp_host, port, timeout=15) as smtp:
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.sendmail(settings.email_from_address, [to_address], msg.as_string())

        logger.info("email_service SMTP sent to %s via %s", to_address, settings.smtp_host)
        return {"success": True, "provider_message_id": None, "error": None}

    except Exception as exc:
        logger.error("email_service SMTP send failed to %s: %s", to_address, exc)
        return {"success": False, "provider_message_id": None, "error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------
def render_alert_email(alert: dict, app_base_url: str) -> tuple[str, str]:
    """
    Render subject and HTML body for a security alert email.
    Returns (subject, html_body).
    """
    severity = alert.get("severity", "")
    category = alert.get("category", "")
    title = alert.get("title", "Security Alert")
    description = alert.get("description", "")
    detected_plate = alert.get("detected_plate", "N/A")
    alert_id = alert.get("id", "")
    detected_at = alert.get("first_detected_at", "")
    if hasattr(detected_at, "strftime"):
        detected_at = detected_at.strftime("%d %b %Y %H:%M:%S IST")

    severity_color = {
        "CRITICAL": "#dc2626",
        "HIGH": "#ea580c",
        "MEDIUM": "#ca8a04",
        "LOW": "#2563eb",
    }.get(severity, "#6b7280")

    alert_url = f"{app_base_url}/security/alerts" if app_base_url else "#"

    subject = f"[SmartGuard AI] {severity} Alert — {title[:80]}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>SmartGuard AI Security Alert</title></head>
<body style="font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#1e293b;border-radius:12px;overflow:hidden;">
    <div style="background:#312e81;padding:24px 32px;border-bottom:3px solid {severity_color};">
      <h1 style="margin:0;font-size:22px;color:#c7d2fe;">🛡 SmartGuard AI</h1>
      <p style="margin:4px 0 0;color:#a5b4fc;font-size:14px;">Security Operations Center</p>
    </div>
    <div style="padding:32px;">
      <div style="background:#0f172a;border-left:4px solid {severity_color};border-radius:6px;padding:16px 20px;margin-bottom:24px;">
        <span style="display:inline-block;background:{severity_color};color:#fff;font-size:11px;font-weight:bold;padding:2px 8px;border-radius:4px;letter-spacing:1px;">{severity}</span>
        <span style="display:inline-block;background:#334155;color:#94a3b8;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px;">{category.replace('_', ' ')}</span>
        <h2 style="color:#f1f5f9;margin:12px 0 6px;font-size:18px;">{title}</h2>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:8px 0;color:#64748b;width:40%;">Plate Detected</td><td style="padding:8px 0;color:#f1f5f9;font-weight:bold;">{detected_plate}</td></tr>
        <tr><td style="padding:8px 0;color:#64748b;">Detected At</td><td style="padding:8px 0;color:#f1f5f9;">{detected_at}</td></tr>
        <tr><td style="padding:8px 0;color:#64748b;">Alert ID</td><td style="padding:8px 0;color:#94a3b8;font-size:12px;">{alert_id}</td></tr>
      </table>
      <div style="background:#0f172a;border-radius:6px;padding:16px;margin-top:20px;">
        <p style="color:#94a3b8;font-size:13px;margin:0;">{description}</p>
      </div>
      <div style="margin-top:28px;text-align:center;">
        <a href="{alert_url}" style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">View Alert in SmartGuard AI</a>
      </div>
    </div>
    <div style="background:#0f172a;padding:16px 32px;text-align:center;">
      <p style="color:#475569;font-size:12px;margin:0;">SmartGuard AI · Automated Security Notification · Do not reply to this email.</p>
    </div>
  </div>
</body>
</html>"""
    return subject, html


def render_daily_summary_email(summary: dict, date_str: str, app_base_url: str) -> tuple[str, str]:
    """
    Render subject and HTML body for a daily security summary email.
    Returns (subject, html_body).
    """
    subject = f"[SmartGuard AI] Daily Security Summary — {date_str}"
    report_url = f"{app_base_url}/admin/reports/daily-summary" if app_base_url else "#"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>SmartGuard AI Daily Summary</title></head>
<body style="font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;margin:0;">
  <div style="max-width:640px;margin:0 auto;background:#1e293b;border-radius:12px;overflow:hidden;">
    <div style="background:#312e81;padding:24px 32px;">
      <h1 style="margin:0;font-size:22px;color:#c7d2fe;">🛡 SmartGuard AI</h1>
      <p style="margin:4px 0 0;color:#a5b4fc;font-size:14px;">Daily Security Summary — {date_str}</p>
    </div>
    <div style="padding:32px;">
      <h2 style="color:#f1f5f9;margin:0 0 20px;font-size:16px;">Access Activity</h2>
      <table style="width:100%;border-collapse:collapse;font-size:14px;background:#0f172a;border-radius:8px;overflow:hidden;">
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#64748b;">Total Attempts</td><td style="padding:10px 16px;color:#f1f5f9;text-align:right;font-weight:bold;">{summary.get("total", 0)}</td></tr>
        <tr><td style="padding:10px 16px;color:#4ade80;">Allowed</td><td style="padding:10px 16px;color:#4ade80;text-align:right;font-weight:bold;">{summary.get("allowed", 0)}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#f87171;">Denied</td><td style="padding:10px 16px;color:#f87171;text-align:right;font-weight:bold;">{summary.get("denied", 0)}</td></tr>
        <tr><td style="padding:10px 16px;color:#fbbf24;">Manual Review</td><td style="padding:10px 16px;color:#fbbf24;text-align:right;font-weight:bold;">{summary.get("manual_review", 0)}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#94a3b8;">Entry</td><td style="padding:10px 16px;text-align:right;">{summary.get("entry", 0)}</td></tr>
        <tr><td style="padding:10px 16px;color:#94a3b8;">Exit</td><td style="padding:10px 16px;text-align:right;">{summary.get("exit", 0)}</td></tr>
      </table>
      <h2 style="color:#f1f5f9;margin:24px 0 12px;font-size:16px;">Security Activity</h2>
      <table style="width:100%;border-collapse:collapse;font-size:14px;background:#0f172a;border-radius:8px;overflow:hidden;">
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#64748b;">New Alerts</td><td style="padding:10px 16px;text-align:right;">{summary.get("new_alerts", 0)}</td></tr>
        <tr><td style="padding:10px 16px;color:#f87171;">Unresolved Alerts</td><td style="padding:10px 16px;color:#f87171;text-align:right;font-weight:bold;">{summary.get("unresolved_alerts", 0)}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#64748b;">Watchlist Incidents</td><td style="padding:10px 16px;text-align:right;">{summary.get("watchlist_incidents", 0)}</td></tr>
        <tr><td style="padding:10px 16px;color:#64748b;">Repeated Denials</td><td style="padding:10px 16px;text-align:right;">{summary.get("repeated_denials", 0)}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:10px 16px;color:#fbbf24;">Pending Reviews</td><td style="padding:10px 16px;color:#fbbf24;text-align:right;">{summary.get("pending_reviews", 0)}</td></tr>
      </table>
      <div style="margin-top:28px;text-align:center;">
        <a href="{report_url}" style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">View Full Report</a>
      </div>
    </div>
    <div style="background:#0f172a;padding:16px 32px;text-align:center;">
      <p style="color:#475569;font-size:12px;margin:0;">SmartGuard AI · Automated Daily Summary · Do not reply to this email.</p>
    </div>
  </div>
</body>
</html>"""
    return subject, html
