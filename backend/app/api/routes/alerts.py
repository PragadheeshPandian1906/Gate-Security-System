"""
SmartGuard AI — Phase 4 Alerts API Routes

GET    /api/alerts                     — list alerts (filtered, paginated)
GET    /api/alerts/metrics             — dashboard metrics
GET    /api/alerts/{id}                — alert detail with notes
POST   /api/alerts/{id}/acknowledge    — OPEN → ACKNOWLEDGED
POST   /api/alerts/{id}/investigate    — OPEN|ACK → INVESTIGATING
POST   /api/alerts/{id}/note           — add investigation note
POST   /api/alerts/{id}/resolve        — → RESOLVED (requires reason)
POST   /api/alerts/{id}/dismiss        — ADMIN only → DISMISSED
"""
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sqla_func
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_security, require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.alerts import SecurityAlert, AlertNote
from app.schemas.alerts import (
    AlertSummary,
    AlertDetail,
    AlertNoteSchema,
    AlertMetrics,
    AlertListResponse,
    AlertLifecycleAction,
    AddAlertNoteRequest,
)
from app.services import alert_service

logger = logging.getLogger("smartguard.alerts_api")
router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_summary(row: SecurityAlert) -> AlertSummary:
    return AlertSummary(
        id=str(row.id),
        category=row.category,
        severity=row.severity,
        title=row.title,
        status=row.status,
        detected_plate=row.detected_plate,
        person_id=str(row.person_id) if row.person_id else None,
        vehicle_id=str(row.vehicle_id) if row.vehicle_id else None,
        access_attempt_id=str(row.access_attempt_id) if row.access_attempt_id else None,
        first_detected_at=row.first_detected_at,
        last_updated_at=row.last_updated_at,
        occurrence_count=row.occurrence_count or 1,
    )


def _to_detail(row: SecurityAlert) -> AlertDetail:
    notes = [
        AlertNoteSchema(
            id=str(n.id),
            alert_id=str(n.alert_id),
            author_id=str(n.author_id) if n.author_id else None,
            note_type=n.note_type,
            body=n.body,
            created_at=n.created_at,
        )
        for n in (row.notes or [])
    ]
    return AlertDetail(
        **_to_summary(row).model_dump(),
        description=row.description,
        watchlist_entry_id=str(row.watchlist_entry_id) if row.watchlist_entry_id else None,
        related_attempt_ids=list(row.related_attempt_ids or []),
        assigned_to=str(row.assigned_to) if row.assigned_to else None,
        acknowledged_by=str(row.acknowledged_by) if row.acknowledged_by else None,
        acknowledged_at=row.acknowledged_at,
        resolved_by=str(row.resolved_by) if row.resolved_by else None,
        resolved_at=row.resolved_at,
        resolution_reason=row.resolution_reason,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/metrics", response_model=AlertMetrics)
def get_alert_metrics(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Alert dashboard metrics — counts by status and severity."""
    return AlertMetrics(**alert_service.get_alert_metrics(db))


@router.get("", response_model=AlertListResponse)
def list_alerts(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    severity: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    alert_status: Optional[str] = Query(default=None, alias="status"),
    plate: Optional[str] = Query(default=None, description="Filter by detected plate (partial)"),
    date_from: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
):
    """List alerts with filtering, sorting, and pagination."""
    from datetime import datetime, timezone

    stmt = select(SecurityAlert).order_by(SecurityAlert.first_detected_at.desc())

    if severity:
        stmt = stmt.where(SecurityAlert.severity == severity.upper())
    if category:
        stmt = stmt.where(SecurityAlert.category == category.upper())
    if alert_status:
        stmt = stmt.where(SecurityAlert.status == alert_status.upper())
    if plate:
        stmt = stmt.where(SecurityAlert.detected_plate.ilike(f"%{plate.upper()}%"))
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            stmt = stmt.where(SecurityAlert.first_detected_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            from datetime import timedelta
            dt_to = dt_to + timedelta(days=1)
            stmt = stmt.where(SecurityAlert.first_detected_at < dt_to)
        except ValueError:
            pass

    total = db.execute(
        select(sqla_func.count()).select_from(stmt.subquery())
    ).scalar() or 0
    rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

    return AlertListResponse(
        items=[_to_summary(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert_detail(
    alert_id: str,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Retrieve full alert detail including investigation notes."""
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID format.")

    row = db.execute(
        select(SecurityAlert).where(SecurityAlert.id == uid)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    # Eager load notes (relationship already sorted by created_at)
    _ = row.notes  # trigger lazy load

    return _to_detail(row)


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Acknowledge an OPEN alert."""
    result = alert_service.acknowledge_alert(db, alert_id, str(account.id))
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alert_id}/investigate")
def start_investigation(
    alert_id: str,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Start investigation on an OPEN or ACKNOWLEDGED alert."""
    result = alert_service.start_investigation(db, alert_id, str(account.id))
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alert_id}/note")
def add_note(
    alert_id: str,
    body: AddAlertNoteRequest,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Add an investigation note to an alert."""
    result = alert_service.add_investigation_note(db, alert_id, str(account.id), body.note)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    body: AlertLifecycleAction,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Resolve an alert. Requires a mandatory resolution reason."""
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="A resolution reason is required.")
    result = alert_service.resolve_alert(db, alert_id, str(account.id), body.reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: str,
    body: AlertLifecycleAction,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Dismiss an alert. ADMIN only."""
    result = alert_service.dismiss_alert(db, alert_id, str(account.id), body.reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
