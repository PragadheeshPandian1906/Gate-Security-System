"""
SmartGuard AI — Access Schedule API Routes (Phase 3)

GET /api/access/schedule  — retrieve current weekly schedule
PUT /api/access/schedule  — update the full schedule (admin only)
"""
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_admin, require_security
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.access import AccessSchedule
from app.schemas.access import ScheduleEntry, ScheduleResponse, ScheduleUpdateRequest

logger = logging.getLogger("smartguard.schedule_api")
router = APIRouter(prefix="/access", tags=["schedule"])

_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@router.get("/schedule", response_model=ScheduleResponse)
def get_schedule(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return the full weekly access schedule with today's status."""
    rows = db.execute(
        select(AccessSchedule).order_by(AccessSchedule.weekday)
    ).scalars().all()

    if not rows:
        raise HTTPException(status_code=503, detail="No access schedule configured.")

    campus_tz_str = rows[0].campus_timezone or "Asia/Kolkata"
    try:
        import zoneinfo
        campus_tz = zoneinfo.ZoneInfo(campus_tz_str)
    except Exception:
        campus_tz_str = "Asia/Kolkata"
        import zoneinfo
        campus_tz = zoneinfo.ZoneInfo(campus_tz_str)

    now_local = datetime.now(campus_tz)
    today_weekday = _WEEKDAY_NAMES[now_local.weekday()]

    schedule_map = {r.weekday: r for r in rows}
    today_row = schedule_map.get(today_weekday)

    entries = [
        ScheduleEntry(
            id=str(r.id),
            weekday=r.weekday,
            is_open=r.is_open,
            open_time=r.open_time,
            close_time=r.close_time,
            campus_timezone=r.campus_timezone,
        )
        for r in sorted(rows, key=lambda x: _WEEKDAY_NAMES.index(x.weekday))
    ]

    return ScheduleResponse(
        entries=entries,
        campus_timezone=campus_tz_str,
        current_local_time=now_local.strftime("%Y-%m-%d %H:%M:%S"),
        today_weekday=today_weekday,
        today_is_open=today_row.is_open if today_row else False,
        today_open_time=today_row.open_time if today_row else None,
        today_close_time=today_row.close_time if today_row else None,
    )


@router.put("/schedule", response_model=ScheduleResponse)
def update_schedule(
    body: ScheduleUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """
    Replace the entire weekly schedule.
    Admin only. Validates that open days have valid start < end times.
    """
    # Validate entries
    weekdays_seen = set()
    for entry in body.entries:
        wd = entry.weekday.lower()
        if wd not in _WEEKDAY_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid weekday: {entry.weekday!r}",
            )
        if wd in weekdays_seen:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate weekday in schedule: {entry.weekday!r}",
            )
        weekdays_seen.add(wd)
        if entry.is_open:
            if not entry.open_time or not entry.close_time:
                raise HTTPException(
                    status_code=400,
                    detail=f"Open day {entry.weekday} must have open_time and close_time.",
                )
            oh, om = map(int, entry.open_time.split(":"))
            ch, cm = map(int, entry.close_time.split(":"))
            if oh * 60 + om >= ch * 60 + cm:
                raise HTTPException(
                    status_code=400,
                    detail=f"open_time must be before close_time for {entry.weekday}.",
                )

    # Validate timezone
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(body.campus_timezone)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid campus_timezone: {body.campus_timezone!r}",
        )

    # Update or insert each row
    existing = {r.weekday: r for r in db.execute(select(AccessSchedule)).scalars().all()}
    for entry in body.entries:
        wd = entry.weekday.lower()
        if wd in existing:
            row = existing[wd]
            row.is_open = entry.is_open
            row.open_time = entry.open_time if entry.is_open else None
            row.close_time = entry.close_time if entry.is_open else None
            row.campus_timezone = body.campus_timezone
            row.updated_by = account.id
        else:
            import uuid as _uuid
            row = AccessSchedule(
                id=_uuid.uuid4(),
                weekday=wd,
                is_open=entry.is_open,
                open_time=entry.open_time if entry.is_open else None,
                close_time=entry.close_time if entry.is_open else None,
                campus_timezone=body.campus_timezone,
                updated_by=account.id,
            )
            db.add(row)

    db.commit()
    logger.info("schedule Updated by admin=%s timezone=%s", account.id, body.campus_timezone)
    return get_schedule(db=db, _account=account)
