"""
SmartGuard AI — Access Schedule Service (Phase 3)

Evaluates whether an access attempt is within the configured schedule.
All time comparisons are performed in the campus timezone.
Invalid or missing configuration → SCHEDULE_UNAVAILABLE (fail-closed).
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("smartguard.schedule")

# Weekday name mapping: Python's weekday() → schedule weekday string
_WEEKDAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]


def _load_schedule(db) -> list:
    """Load all schedule rows from DB. Returns empty list on failure."""
    try:
        from sqlalchemy import select
        from app.models.access import AccessSchedule
        rows = db.execute(select(AccessSchedule)).scalars().all()
        return list(rows)
    except Exception as exc:
        logger.error("schedule Failed to load schedule from DB: %s", exc)
        return []


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute). Raises ValueError on bad format."""
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str!r}")
    return int(parts[0]), int(parts[1])


def evaluate_schedule(db, at_time: Optional[datetime] = None) -> dict:
    """
    Evaluate whether *at_time* (defaults to now) is within the schedule.

    Returns a dict with:
        ok          : bool — True if access is permitted
        reason_code : str  — 'SCHEDULE_OK' | 'OUTSIDE_SCHEDULE' | 'SCHEDULE_UNAVAILABLE'
        detail      : str  — human-readable explanation
        evaluated_local : str — local datetime string used for evaluation
        weekday     : str  — weekday name
        schedule_open_time  : str | None
        schedule_close_time : str | None
        campus_timezone : str
    """
    rows = _load_schedule(db)
    if not rows:
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": "Access schedule configuration is missing. Fail-closed.",
            "evaluated_local": "",
            "weekday": "",
            "schedule_open_time": None,
            "schedule_close_time": None,
            "campus_timezone": "Asia/Kolkata",
        }

    # Build a dict keyed by weekday name
    schedule_map = {r.weekday: r for r in rows}

    # Determine campus timezone from first row (all rows share the same tz)
    campus_tz_str = rows[0].campus_timezone or "Asia/Kolkata"
    try:
        import zoneinfo
        campus_tz = zoneinfo.ZoneInfo(campus_tz_str)
    except Exception as exc:
        logger.error("schedule Invalid campus timezone %r: %s", campus_tz_str, exc)
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": f"Campus timezone {campus_tz_str!r} is invalid: {exc}",
            "evaluated_local": "",
            "weekday": "",
            "schedule_open_time": None,
            "schedule_close_time": None,
            "campus_timezone": campus_tz_str,
        }

    # Convert evaluation time to campus local time
    if at_time is None:
        at_time = datetime.now(campus_tz)
    else:
        at_time = at_time.astimezone(campus_tz)

    local_str = at_time.strftime("%Y-%m-%d %H:%M:%S %Z")
    weekday_name = _WEEKDAY_NAMES[at_time.weekday()]

    row = schedule_map.get(weekday_name)
    if row is None:
        logger.warning("schedule No schedule row for weekday=%r", weekday_name)
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": f"No schedule configured for {weekday_name}.",
            "evaluated_local": local_str,
            "weekday": weekday_name,
            "schedule_open_time": None,
            "schedule_close_time": None,
            "campus_timezone": campus_tz_str,
        }

    if not row.is_open:
        return {
            "ok": False,
            "reason_code": "OUTSIDE_SCHEDULE",
            "detail": f"{weekday_name.capitalize()} is a closed day.",
            "evaluated_local": local_str,
            "weekday": weekday_name,
            "schedule_open_time": None,
            "schedule_close_time": None,
            "campus_timezone": campus_tz_str,
        }

    if not row.open_time or not row.close_time:
        logger.error("schedule Weekday %r is_open=True but times are missing", weekday_name)
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": f"Schedule for {weekday_name} is misconfigured (missing open/close times).",
            "evaluated_local": local_str,
            "weekday": weekday_name,
            "schedule_open_time": row.open_time,
            "schedule_close_time": row.close_time,
            "campus_timezone": campus_tz_str,
        }

    try:
        open_h, open_m = _parse_time(row.open_time)
        close_h, close_m = _parse_time(row.close_time)
    except ValueError as exc:
        logger.error("schedule Time parse error for %r: %s", weekday_name, exc)
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": f"Schedule time format error for {weekday_name}: {exc}",
            "evaluated_local": local_str,
            "weekday": weekday_name,
            "schedule_open_time": row.open_time,
            "schedule_close_time": row.close_time,
            "campus_timezone": campus_tz_str,
        }

    current_minutes = at_time.hour * 60 + at_time.minute
    open_minutes = open_h * 60 + open_m
    close_minutes = close_h * 60 + close_m

    if open_minutes >= close_minutes:
        logger.error("schedule open_time >= close_time for %r — misconfigured", weekday_name)
        return {
            "ok": False,
            "reason_code": "SCHEDULE_UNAVAILABLE",
            "detail": f"Schedule misconfigured for {weekday_name}: open_time must be before close_time.",
            "evaluated_local": local_str,
            "weekday": weekday_name,
            "schedule_open_time": row.open_time,
            "schedule_close_time": row.close_time,
            "campus_timezone": campus_tz_str,
        }

    within = open_minutes <= current_minutes < close_minutes

    return {
        "ok": within,
        "reason_code": "SCHEDULE_OK" if within else "OUTSIDE_SCHEDULE",
        "detail": (
            f"Access permitted: {row.open_time}–{row.close_time} {campus_tz_str}"
            if within
            else (
                f"Outside access hours ({row.open_time}–{row.close_time} {campus_tz_str}). "
                f"Current time: {at_time.strftime('%H:%M')} {campus_tz_str}."
            )
        ),
        "evaluated_local": local_str,
        "weekday": weekday_name,
        "schedule_open_time": row.open_time,
        "schedule_close_time": row.close_time,
        "campus_timezone": campus_tz_str,
    }
