"""
SmartGuard AI — Watchlist API Routes (Phase 3)

GET    /api/watchlist          — list watchlist entries
POST   /api/watchlist          — create a new watchlist entry
PATCH  /api/watchlist/{id}     — update/deactivate an entry
DELETE /api/watchlist/{id}     — deactivate (soft delete) an entry
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_security
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.access import WatchlistEntry
from app.schemas.access import (
    WatchlistEntryCreate,
    WatchlistEntryResponse,
    WatchlistEntryUpdate,
)
from app.services.alpr_service import normalize_plate

logger = logging.getLogger("smartguard.watchlist_api")
router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _to_response(e: WatchlistEntry) -> WatchlistEntryResponse:
    return WatchlistEntryResponse(
        id=str(e.id),
        vehicle_id=str(e.vehicle_id) if e.vehicle_id else None,
        plate_raw=e.plate_raw,
        plate_normalized=e.plate_normalized,
        reason=e.reason,
        severity=e.severity,
        is_active=e.is_active,
        expires_at=e.expires_at,
        resolved_at=e.resolved_at,
        resolution_note=e.resolution_note,
        created_at=e.created_at,
        created_by=str(e.created_by) if e.created_by else None,
        resolved_by=str(e.resolved_by) if e.resolved_by else None,
    )


@router.get("", response_model=list[WatchlistEntryResponse])
def list_watchlist(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    active_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List watchlist entries. Filter by active_only if needed."""
    stmt = select(WatchlistEntry).order_by(WatchlistEntry.created_at.desc()).offset(skip).limit(limit)
    if active_only:
        stmt = stmt.where(WatchlistEntry.is_active == True)  # noqa: E712
    rows = db.execute(stmt).scalars().all()
    return [_to_response(r) for r in rows]


@router.post("", response_model=WatchlistEntryResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist_entry(
    body: WatchlistEntryCreate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Add a vehicle or plate to the watchlist."""
    if not body.vehicle_id and not body.plate_raw:
        raise HTTPException(
            status_code=400,
            detail="Either vehicle_id or plate_raw must be provided.",
        )

    # Resolve vehicle_id and normalize plate
    vehicle_id = None
    plate_raw = body.plate_raw
    plate_norm = normalize_plate(plate_raw) if plate_raw else None

    if body.vehicle_id:
        try:
            vehicle_id = uuid.UUID(body.vehicle_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid vehicle_id format.")

        # Load the vehicle's plate to populate plate_normalized
        from sqlalchemy import select as sa_select
        from app.models.people import Vehicle
        veh = db.execute(sa_select(Vehicle).where(Vehicle.id == vehicle_id)).scalar_one_or_none()
        if veh is None:
            raise HTTPException(status_code=404, detail="Vehicle not found.")
        plate_raw = plate_raw or veh.plate_number
        plate_norm = veh.plate_normalized

    entry = WatchlistEntry(
        id=uuid.uuid4(),
        vehicle_id=vehicle_id,
        plate_raw=plate_raw,
        plate_normalized=plate_norm,
        reason=body.reason,
        severity=body.severity,
        is_active=True,
        expires_at=body.expires_at,
        created_by=account.id,
    )
    db.add(entry)

    # Also set vehicle.status = 'flagged' if a vehicle_id is provided
    if vehicle_id:
        from app.models.people import Vehicle
        from sqlalchemy import select as sa_select
        veh = db.execute(sa_select(Vehicle).where(Vehicle.id == vehicle_id)).scalar_one_or_none()
        if veh and veh.status != "flagged":
            veh.status = "flagged"

    db.commit()
    db.refresh(entry)
    logger.info("watchlist Created entry=%s plate=%s severity=%s by=%s", entry.id, plate_norm, body.severity, account.id)
    return _to_response(entry)


@router.patch("/{entry_id}", response_model=WatchlistEntryResponse)
def update_watchlist_entry(
    entry_id: str,
    body: WatchlistEntryUpdate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Update or deactivate a watchlist entry."""
    try:
        uid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry ID.")

    entry = db.execute(select(WatchlistEntry).where(WatchlistEntry.id == uid)).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")

    if body.reason is not None:
        entry.reason = body.reason
    if body.severity is not None:
        entry.severity = body.severity
    if body.expires_at is not None:
        entry.expires_at = body.expires_at
    if body.resolution_note is not None:
        entry.resolution_note = body.resolution_note
    if body.is_active is not None:
        entry.is_active = body.is_active
        if not body.is_active and not entry.resolved_at:
            entry.resolved_at = datetime.now(timezone.utc)
            entry.resolved_by = account.id

    db.commit()
    db.refresh(entry)
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_200_OK)
def deactivate_watchlist_entry(
    entry_id: str,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Deactivate (soft-delete) a watchlist entry to preserve audit trail."""
    try:
        uid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry ID.")

    entry = db.execute(select(WatchlistEntry).where(WatchlistEntry.id == uid)).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")

    entry.is_active = False
    entry.resolved_at = datetime.now(timezone.utc)
    entry.resolved_by = account.id
    db.commit()
    logger.info("watchlist Deactivated entry=%s by=%s", entry_id, account.id)
    return {"message": "Watchlist entry deactivated.", "id": entry_id}
