"""Campus-wide access analytics based on the access-decision audit trail."""
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, aliased

from app.models.access import AccessAttempt, AccessSchedule
from app.models.people import CampusPerson, PERSON_TYPE_VALUES
from app.models.visitors import VisitorPass
from app.schemas.access import (
    CampusAccessActivity,
    CampusAnalyticsResponse,
    CampusHourlyAuthorization,
)


MOVEMENT_LIMITATION = (
    "The system records access decisions and gate commands, but has no sensor-confirmed "
    "person-crossing event. Visitor pass approval/check-in is not proof of entry, so "
    "entry, exit, current occupancy, and occupancy by category are unavailable."
)


class CampusTimezoneConfigurationError(ValueError):
    """Raised when the configured campus timezone is not a valid IANA timezone."""


def local_day_utc_bounds(
    at_time: datetime, campus_timezone: str
) -> tuple[datetime, datetime]:
    """Return inclusive-start/exclusive-end UTC bounds for the campus-local day."""
    try:
        local_zone = ZoneInfo(campus_timezone)
    except ZoneInfoNotFoundError as exc:
        raise CampusTimezoneConfigurationError(
            f"Invalid campus timezone: {campus_timezone!r}"
        ) from exc

    if at_time.tzinfo is None:
        raise ValueError("Analytics reference time must be timezone-aware.")

    local_date = at_time.astimezone(local_zone).date()
    next_date = local_date + timedelta(days=1)
    start_local = datetime.combine(local_date, time.min, tzinfo=local_zone)
    end_local = datetime.combine(next_date, time.min, tzinfo=local_zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def get_campus_analytics(
    db: Session, at_time: datetime | None = None
) -> CampusAnalyticsResponse:
    """Aggregate today's access decisions and return recent audit activity."""
    timezone_result = db.execute(
        select(AccessSchedule.campus_timezone)
        .order_by(AccessSchedule.updated_at.desc())
        .limit(1)
    )
    campus_timezone = timezone_result.scalar_one_or_none() or "Asia/Kolkata"
    reference_time = at_time or datetime.now(timezone.utc)
    start_utc, end_utc = local_day_utc_bounds(reference_time, campus_timezone)

    local_hour = extract(
        "hour", func.timezone(campus_timezone, AccessAttempt.timestamp)
    ).label("hour")
    grouped_rows = db.execute(
        select(
            AccessAttempt.direction,
            AccessAttempt.decision,
            local_hour,
            func.count().label("attempt_count"),
        )
        .where(
            AccessAttempt.timestamp >= start_utc,
            AccessAttempt.timestamp < end_utc,
        )
        .group_by(AccessAttempt.direction, AccessAttempt.decision, local_hour)
    ).all()

    denied_count = 0
    hourly_counts = {
        hour: {"ENTRY": 0, "EXIT": 0}
        for hour in range(24)
    }
    for direction, decision, hour, count in grouped_rows:
        if decision == "DENY":
            denied_count += count
        elif decision == "ALLOW" and direction in ("ENTRY", "EXIT"):
            hourly_counts[int(hour)][direction] += count

    visitor_pass = aliased(VisitorPass)
    visitor_person = aliased(CampusPerson)
    matched_person = aliased(CampusPerson)
    recent_rows = db.execute(
        select(
            AccessAttempt.id,
            AccessAttempt.timestamp,
            func.coalesce(visitor_person.full_name, matched_person.full_name),
            func.coalesce(visitor_person.person_type, matched_person.person_type),
            AccessAttempt.direction,
            AccessAttempt.decision,
        )
        .outerjoin(
            matched_person,
            matched_person.id
            == func.coalesce(
                AccessAttempt.matched_person_id,
                AccessAttempt.vehicle_owner_person_id,
            ),
        )
        .outerjoin(visitor_pass, visitor_pass.id == AccessAttempt.visitor_pass_id)
        .outerjoin(visitor_person, visitor_person.id == visitor_pass.visitor_id)
        .order_by(AccessAttempt.timestamp.desc())
        .limit(20)
    ).all()

    activity = [
        CampusAccessActivity(
            id=str(attempt_id) if isinstance(attempt_id, uuid.UUID) else attempt_id,
            timestamp=timestamp,
            person_name=person_name,
            person_category=person_category,
            direction=direction or "UNKNOWN",
            decision=decision,
        )
        for (
            attempt_id,
            timestamp,
            person_name,
            person_category,
            direction,
            decision,
        ) in recent_rows
    ]
    hourly_activity = [
        CampusHourlyAuthorization(
            hour=hour,
            entry_authorizations=hourly_counts[hour]["ENTRY"],
            exit_authorizations=hourly_counts[hour]["EXIT"],
        )
        for hour in range(24)
    ]

    return CampusAnalyticsResponse(
        campus_timezone=campus_timezone,
        movement_limitation=MOVEMENT_LIMITATION,
        denied_access_today=denied_count,
        supported_person_categories=list(PERSON_TYPE_VALUES),
        hourly_activity=hourly_activity,
        recent_activity=activity,
    )
