"""
SmartGuard AI — Phase 4 Reports API Routes

GET  /api/reports/access           — filtered, paginated access report
GET  /api/reports/access/export    — CSV export with same filters
GET  /api/reports/daily-summary    — daily security summary
POST /api/reports/daily-summary/send — manually send daily summary email
"""
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func as sqla_func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_security, require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.access import AccessAttempt
from app.models.alerts import SecurityAlert, AlertNote
from app.models.visitors import VisitorPass
from app.schemas.alerts import (
    AccessReportRow,
    AccessReportResponse,
    DailySummaryResponse,
    SendDailySummaryRequest,
)

logger = logging.getLogger("smartguard.reports_api")
router = APIRouter(prefix="/reports", tags=["reports"])

# Campus timezone
CAMPUS_TZ_NAME = "Asia/Kolkata"


# ---------------------------------------------------------------------------
# Helper: build base access query from filters
# ---------------------------------------------------------------------------
def _build_access_query(
    direction: Optional[str],
    decision: Optional[str],
    plate: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    watchlist_only: bool,
    review_pending: bool,
    visitors_only: bool = False,
):
    stmt = select(AccessAttempt).order_by(AccessAttempt.timestamp.desc())

    if direction:
        stmt = stmt.where(AccessAttempt.direction == direction.upper())
    if decision:
        stmt = stmt.where(AccessAttempt.decision == decision.upper())
    if plate:
        plate_up = plate.upper().replace(" ", "")
        stmt = stmt.where(
            or_(
                AccessAttempt.detected_plate.ilike(f"%{plate}%"),
                AccessAttempt.detected_plate_normalized.ilike(f"%{plate_up}%"),
            )
        )
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            stmt = stmt.where(AccessAttempt.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            stmt = stmt.where(AccessAttempt.timestamp < dt_to)
        except ValueError:
            pass
    if watchlist_only:
        stmt = stmt.where(AccessAttempt.watchlist_hit == True)  # noqa: E712
    if review_pending:
        stmt = stmt.where(
            AccessAttempt.review_required == True,  # noqa: E712
            AccessAttempt.review_resolved == False,  # noqa: E712
        )
    if visitors_only:
        stmt = stmt.where(AccessAttempt.visitor_pass_id != None)  # noqa: E711
    return stmt


def _row_to_schema(row: AccessAttempt, db: Optional[Session] = None) -> AccessReportRow:
    import json
    codes = row.reason_codes
    if isinstance(codes, str):
        try:
            codes = json.loads(codes)
        except Exception:
            codes = []

    pass_number = None
    if row.visitor_pass_id and db is not None:
        vpass = db.get(VisitorPass, row.visitor_pass_id)
        if vpass:
            pass_number = vpass.pass_number

    return AccessReportRow(
        id=str(row.id),
        timestamp=row.timestamp,
        direction=row.direction,
        decision=row.decision,
        gate_result=row.gate_result,
        reason_codes=codes or [],
        reason_text=row.reason_text,
        detected_plate=row.detected_plate,
        detected_plate_normalized=row.detected_plate_normalized,
        matched_person_id=str(row.matched_person_id) if row.matched_person_id else None,
        person_status=row.person_status,
        matched_vehicle_id=str(row.matched_vehicle_id) if row.matched_vehicle_id else None,
        vehicle_status=row.vehicle_status,
        ownership_ok=row.ownership_ok,
        schedule_ok=row.schedule_ok,
        watchlist_hit=row.watchlist_hit,
        watchlist_severity=row.watchlist_severity,
        review_required=row.review_required,
        review_resolved=row.review_resolved,
        review_resolution=row.review_resolution,
        review_reason=row.review_reason,
        initiated_by=str(row.initiated_by) if row.initiated_by else None,
        processing_ms=row.processing_ms,
        visitor_pass_id=str(row.visitor_pass_id) if row.visitor_pass_id else None,
        visitor_pass_number=pass_number,
    )


# ---------------------------------------------------------------------------
# Access Report
# ---------------------------------------------------------------------------
@router.get("/access", response_model=AccessReportResponse)
def list_access_report(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    direction: Optional[str] = Query(default=None),
    decision: Optional[str] = Query(default=None),
    plate: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    watchlist_only: bool = Query(default=False),
    review_pending: bool = Query(default=False),
    visitors_only: bool = Query(default=False),
):
    """Filtered, server-side paginated access report."""
    stmt = _build_access_query(direction, decision, plate, date_from, date_to, watchlist_only, review_pending, visitors_only)

    total = db.execute(
        select(sqla_func.count()).select_from(stmt.subquery())
    ).scalar() or 0
    rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

    return AccessReportResponse(
        items=[_row_to_schema(r, db) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/access/export")
def export_access_report_csv(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    direction: Optional[str] = Query(default=None),
    decision: Optional[str] = Query(default=None),
    plate: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    watchlist_only: bool = Query(default=False),
    review_pending: bool = Query(default=False),
    visitors_only: bool = Query(default=False),
):
    """Export access records as CSV with same filters. Max 5000 rows per export."""
    stmt = _build_access_query(direction, decision, plate, date_from, date_to, watchlist_only, review_pending, visitors_only)
    rows = db.execute(stmt.limit(5000)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([
        "ID", "Timestamp (IST)", "Direction", "Decision", "Gate Result",
        "Plate Detected", "Plate Normalized", "Watchlist Hit", "Watchlist Severity",
        "Ownership OK", "Schedule OK", "Reason Codes", "Reason Text",
        "Person ID", "Person Status", "Vehicle ID", "Vehicle Status",
        "Visitor Pass ID", "Review Required", "Review Resolved", "Review Resolution",
        "Processing (ms)",
    ])

    import json
    try:
        import zoneinfo
        ist = zoneinfo.ZoneInfo(CAMPUS_TZ_NAME)
    except Exception:
        ist = timezone.utc

    for row in rows:
        codes = row.reason_codes or []
        if isinstance(codes, str):
            try:
                codes = json.loads(codes)
            except Exception:
                codes = []

        ts = row.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_ist = ts.astimezone(ist)

        # Sanitize text fields against CSV formula injection
        def safe(val):
            if val is None:
                return ""
            s = str(val).strip()
            # Prevent formula injection
            if s and s[0] in ("=", "+", "-", "@", "|"):
                s = "'" + s
            return s

        writer.writerow([
            safe(row.id),
            safe(ts_ist.strftime("%Y-%m-%d %H:%M:%S")),
            safe(row.direction),
            safe(row.decision),
            safe(row.gate_result),
            safe(row.detected_plate),
            safe(row.detected_plate_normalized),
            safe("Yes" if row.watchlist_hit else "No"),
            safe(row.watchlist_severity),
            safe("Yes" if row.ownership_ok is True else ("No" if row.ownership_ok is False else "")),
            safe("Yes" if row.schedule_ok is True else ("No" if row.schedule_ok is False else "")),
            safe(", ".join(codes)),
            safe(row.reason_text),
            safe(row.matched_person_id),
            safe(row.person_status),
            safe(row.matched_vehicle_id),
            safe(row.vehicle_status),
            safe(row.visitor_pass_id),
            safe("Yes" if row.review_required else "No"),
            safe("Yes" if row.review_resolved else "No"),
            safe(row.review_resolution),
            safe(row.processing_ms),
        ])

    output.seek(0)
    filename = f"smartguard_access_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Daily Summary
# ---------------------------------------------------------------------------
@router.get("/daily-summary", response_model=DailySummaryResponse)
def get_daily_summary(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD (defaults to today IST)"),
):
    """Compute a daily security summary for the specified campus-local date."""
    summary = _compute_daily_summary(db, date)
    return DailySummaryResponse(**summary)


@router.post("/daily-summary/send")
def send_daily_summary_email(
    body: SendDailySummaryRequest,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Manually trigger a daily summary email send. ADMIN only."""
    from app.services import notification_service
    summary = _compute_daily_summary(db, body.date)
    result = notification_service.send_daily_summary(db, body.date, summary, force=body.force)
    return result


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------
def _compute_daily_summary(db, date_str: Optional[str]) -> dict:
    """Compute daily summary metrics for the given campus-local date."""
    try:
        import zoneinfo
        ist = zoneinfo.ZoneInfo(CAMPUS_TZ_NAME)
    except Exception:
        ist = timezone.utc

    now_ist = datetime.now(ist)

    if date_str:
        try:
            local_day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            local_day = now_ist.date()
    else:
        local_day = now_ist.date()
        date_str = local_day.isoformat()

    # Convert campus-local midnight to UTC for DB queries
    from datetime import date as date_cls
    day_start_local = datetime(local_day.year, local_day.month, local_day.day, 0, 0, 0, tzinfo=ist)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)

    # Access attempts for the day
    base = select(AccessAttempt).where(
        AccessAttempt.timestamp >= day_start_utc,
        AccessAttempt.timestamp < day_end_utc,
    )

    total = db.execute(select(sqla_func.count()).select_from(base.subquery())).scalar() or 0
    allowed = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.decision == "ALLOW",
        )
    ).scalar() or 0
    denied = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.decision == "DENY",
        )
    ).scalar() or 0
    manual = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.decision == "MANUAL_REVIEW",
        )
    ).scalar() or 0
    entry = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.direction == "ENTRY",
        )
    ).scalar() or 0
    exit_ = total - entry

    # Pending reviews (all-time unresolved)
    pending_reviews = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.review_required == True,  # noqa: E712
            AccessAttempt.review_resolved == False,  # noqa: E712
        )
    ).scalar() or 0

    # Reviews resolved today
    resolved_reviews = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.review_resolved == True,  # noqa: E712
            AccessAttempt.reviewed_at >= day_start_utc,
            AccessAttempt.reviewed_at < day_end_utc,
        )
    ).scalar() or 0

    # Alerts
    new_alerts = db.execute(
        select(sqla_func.count(SecurityAlert.id)).where(
            SecurityAlert.first_detected_at >= day_start_utc,
            SecurityAlert.first_detected_at < day_end_utc,
        )
    ).scalar() or 0

    unresolved_alerts = db.execute(
        select(sqla_func.count(SecurityAlert.id)).where(
            SecurityAlert.status.not_in(["RESOLVED", "DISMISSED"])
        )
    ).scalar() or 0

    watchlist_incidents = db.execute(
        select(sqla_func.count(SecurityAlert.id)).where(
            SecurityAlert.first_detected_at >= day_start_utc,
            SecurityAlert.first_detected_at < day_end_utc,
            SecurityAlert.category == "WATCHLIST_HIT",
        )
    ).scalar() or 0

    repeated_denials = db.execute(
        select(sqla_func.count(SecurityAlert.id)).where(
            SecurityAlert.first_detected_at >= day_start_utc,
            SecurityAlert.first_detected_at < day_end_utc,
            SecurityAlert.category == "REPEATED_DENIAL",
        )
    ).scalar() or 0

    # Top denial reasons from reason_codes JSON
    deny_rows = db.execute(
        select(AccessAttempt.reason_codes).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.decision == "DENY",
        )
    ).scalars().all()

    import json
    from collections import Counter
    code_counter: Counter = Counter()
    for codes in deny_rows:
        if isinstance(codes, str):
            try:
                codes = json.loads(codes)
            except Exception:
                codes = []
        if isinstance(codes, list):
            for code in codes:
                if code and code != "ALL_CHECKS_PASSED":
                    code_counter[code] += 1

    top_denial_reasons = [
        {"code": code, "count": cnt}
        for code, cnt in code_counter.most_common(5)
    ]

    # Visitor metrics for the day
    visitor_entries = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.direction == "ENTRY",
            AccessAttempt.visitor_pass_id != None,  # noqa: E711
        )
    ).scalar() or 0

    visitor_exits = db.execute(
        select(sqla_func.count(AccessAttempt.id)).where(
            AccessAttempt.timestamp >= day_start_utc,
            AccessAttempt.timestamp < day_end_utc,
            AccessAttempt.direction == "EXIT",
            AccessAttempt.visitor_pass_id != None,  # noqa: E711
        )
    ).scalar() or 0

    active_visitors_inside = db.execute(
        select(sqla_func.count()).select_from(VisitorPass).where(
            VisitorPass.status == "ACTIVE_INSIDE"
        )
    ).scalar() or 0

    return {
        "date": date_str,
        "timezone": CAMPUS_TZ_NAME,
        "total": total,
        "allowed": allowed,
        "denied": denied,
        "manual_review": manual,
        "entry": entry,
        "exit": exit_,
        "visitor_entries": int(visitor_entries),
        "visitor_exits": int(visitor_exits),
        "active_visitors_inside": int(active_visitors_inside),
        "new_alerts": new_alerts,
        "unresolved_alerts": unresolved_alerts,
        "watchlist_incidents": watchlist_incidents,
        "repeated_denials": repeated_denials,
        "pending_reviews": pending_reviews,
        "resolved_reviews": resolved_reviews,
        "top_denial_reasons": top_denial_reasons,
    }

