"""
SmartGuard AI — Phase 4 Notification Delivery Log API Routes
All endpoints require ADMIN role — enforced via require_admin dependency.

Endpoints:
  GET  /api/admin/notifications           — list notification delivery logs (paginated, filtered)
  POST /api/admin/notifications/{id}/retry — retry a specific failed notification
  POST /api/admin/notifications/retry-all — retry all eligible failed notifications
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sqla_func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.alerts import NotificationLog
from app.schemas.alerts import (
    NotificationListResponse,
    NotificationLogResponse,
)
from app.services import notification_service

router = APIRouter(prefix="/admin/notifications", tags=["Notification Logs"])
logger = logging.getLogger("smartguard.notifications_api")


def _row_to_response(row: NotificationLog) -> NotificationLogResponse:
    return NotificationLogResponse(
        id=str(row.id),
        notification_type=row.notification_type,
        alert_id=str(row.alert_id) if row.alert_id else None,
        contact_id=str(row.contact_id) if row.contact_id else None,
        recipient_email=row.recipient_email,
        subject=row.subject,
        status=row.status,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        created_at=row.created_at,
        last_attempted_at=row.last_attempted_at,
        sent_at=row.sent_at,
        next_retry_at=row.next_retry_at,
        provider=row.provider,
        provider_message_id=row.provider_message_id,
        error_detail=row.error_detail,
        summary_date=row.summary_date,
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (PENDING, SENT, FAILED, RETRY_SCHEDULED)"),
    notification_type: Optional[str] = Query(None, description="Filter by type (ALERT, DAILY_SUMMARY, TEST)"),
    recipient: Optional[str] = Query(None, description="Search recipient email"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _admin: SecurityAccount = Depends(require_admin),
) -> NotificationListResponse:
    """List notification logs with server-side filtering and pagination."""
    query = select(NotificationLog).order_by(NotificationLog.created_at.desc())

    if status_filter:
        query = query.where(NotificationLog.status == status_filter.upper())
    if notification_type:
        query = query.where(NotificationLog.notification_type == notification_type.upper())
    if recipient:
        query = query.where(NotificationLog.recipient_email.ilike(f"%{recipient.strip().lower()}%"))
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.where(NotificationLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            query = query.where(NotificationLog.created_at < dt_to)
        except ValueError:
            pass

    total = db.execute(select(sqla_func.count()).select_from(query.subquery())).scalar() or 0
    rows = db.execute(query.offset(skip).limit(limit)).scalars().all()

    return NotificationListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/{notification_id}/retry", response_model=NotificationLogResponse)
def retry_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> NotificationLogResponse:
    """Manually retry a failed or retry-scheduled notification."""
    notif = db.execute(
        select(NotificationLog).where(NotificationLog.id == notification_id)
    ).scalar_one_or_none()

    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification log not found")

    if notif.status == "SENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot retry a notification that has already been SENT.",
        )

    # Reset attempt status for re-dispatch
    notif.status = "RETRY_SCHEDULED"
    notif.next_retry_at = datetime.now(timezone.utc)
    db.add(notif)
    db.commit()

    # Trigger process attempt
    notification_service._process_pending_notifications(db)
    db.refresh(notif)

    logger.info("Retried notification: id=%s by admin=%s", notif.id, admin.username)
    return _row_to_response(notif)


@router.post("/retry-all")
def retry_all_failed(
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
):
    """Reschedule all eligible failed notifications for retry."""
    result = notification_service.retry_failed_notifications(db)
    logger.info("Rescheduled failed notifications: count=%s by admin=%s", result.get("rescheduled"), admin.username)
    return result
