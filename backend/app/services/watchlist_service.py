"""
SmartGuard AI — Watchlist Service (Phase 3)

Checks whether a detected plate or registered vehicle has an active
watchlist entry. Respects expiry and active/inactive flags.

Decision rules:
  - high severity active entry → WATCHLIST_BLOCK (→ DENY)
  - other severity active entry → WATCHLIST_REVIEW (→ MANUAL_REVIEW)
  - no applicable entry → no watchlist block
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

logger = logging.getLogger("smartguard.watchlist")


def check_watchlist(
    db,
    vehicle_id: Optional[UUID] = None,
    plate_normalized: Optional[str] = None,
) -> dict:
    """
    Check whether the vehicle or plate is on the active watchlist.

    Args:
        db              : SQLAlchemy session
        vehicle_id      : UUID of matched registered vehicle (optional)
        plate_normalized: Normalized plate text (optional)

    Returns a dict with:
        hit          : bool — True if an active entry was found
        severity     : str | None — 'high' | 'medium' | 'low'
        reason_code  : str  — 'WATCHLIST_BLOCK' | 'WATCHLIST_REVIEW' | 'NO_WATCHLIST_HIT'
        reason_text  : str
        entry_id     : str | None — UUID of the matching watchlist entry
        entry_reason : str | None — reason text from the watchlist entry
    """
    if not vehicle_id and not plate_normalized:
        return {
            "hit": False,
            "severity": None,
            "reason_code": "NO_WATCHLIST_HIT",
            "reason_text": "No vehicle or plate to check.",
            "entry_id": None,
            "entry_reason": None,
        }

    try:
        from sqlalchemy import select, or_
        from app.models.access import WatchlistEntry

        now = datetime.now(timezone.utc)

        conditions = []
        if vehicle_id:
            conditions.append(WatchlistEntry.vehicle_id == vehicle_id)
        if plate_normalized:
            conditions.append(WatchlistEntry.plate_normalized == plate_normalized)

        stmt = (
            select(WatchlistEntry)
            .where(
                WatchlistEntry.is_active == True,  # noqa: E712
                or_(*conditions),
            )
            .order_by(
                # Prioritize: high > medium > low, then most recent
                WatchlistEntry.severity.desc(),
                WatchlistEntry.created_at.desc(),
            )
        )
        entries = db.execute(stmt).scalars().all()

        # Filter out expired entries
        active_entries = [
            e for e in entries
            if e.expires_at is None or e.expires_at.replace(tzinfo=timezone.utc) > now
        ]

        if not active_entries:
            return {
                "hit": False,
                "severity": None,
                "reason_code": "NO_WATCHLIST_HIT",
                "reason_text": "No active watchlist restrictions found.",
                "entry_id": None,
                "entry_reason": None,
            }

        # Use the highest-severity entry
        # Sort: high > medium > low
        severity_order = {"high": 3, "medium": 2, "low": 1}
        top = sorted(
            active_entries,
            key=lambda e: severity_order.get(e.severity, 0),
            reverse=True
        )[0]

        if top.severity == "high":
            code = "WATCHLIST_BLOCK"
            text = (
                f"Vehicle is on the high-severity watchlist. "
                f"Reason: {top.reason}. Access denied."
            )
        else:
            code = "WATCHLIST_REVIEW"
            text = (
                f"Vehicle has a {top.severity}-severity watchlist entry. "
                f"Reason: {top.reason}. Manual review required."
            )

        logger.info(
            "watchlist Hit for vehicle_id=%s plate=%s entry_id=%s severity=%s",
            vehicle_id, plate_normalized, top.id, top.severity,
        )

        return {
            "hit": True,
            "severity": top.severity,
            "reason_code": code,
            "reason_text": text,
            "entry_id": str(top.id),
            "entry_reason": top.reason,
        }

    except Exception as exc:
        logger.error("watchlist Check failed: %s", exc, exc_info=True)
        # Fail-closed: treat error as potential watchlist hit requiring review
        return {
            "hit": True,
            "severity": "unknown",
            "reason_code": "WATCHLIST_REVIEW",
            "reason_text": f"Watchlist check failed (database error). Manual review required: {exc}",
            "entry_id": None,
            "entry_reason": None,
        }
