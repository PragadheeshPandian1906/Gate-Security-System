"""
SmartGuard AI — Vehicles API (Phase 2)

Endpoints:
  GET    /api/vehicles            - list vehicles (paginated, filterable)
  POST   /api/vehicles            - register vehicle
  GET    /api/vehicles/{id}       - get vehicle detail
  PATCH  /api/vehicles/{id}       - update vehicle
  DELETE /api/vehicles/{id}       - delete vehicle
"""
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.people import CampusPerson, Vehicle
from app.schemas.people import (
    VehicleCreate,
    VehicleListOut,
    VehicleOut,
    VehicleUpdate,
)
from app.services.alpr_service import normalize_plate

logger = logging.getLogger("smartguard.vehicles")
router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _get_vehicle_or_404(vehicle_id: uuid.UUID, db: Session) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return v


@router.get("", response_model=VehicleListOut)
def list_vehicles(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(get_active_account)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    """List registered vehicles with optional filters."""
    q = select(Vehicle)
    if status:
        q = q.where(Vehicle.status == status)
    if search:
        pattern = f"%{search}%"
        q = q.where(
            (Vehicle.plate_number.ilike(pattern))
            | (Vehicle.owner_name.ilike(pattern))
            | (Vehicle.make.ilike(pattern))
            | (Vehicle.model.ilike(pattern))
        )

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    vehicles = db.execute(
        q.offset(skip).limit(limit).order_by(Vehicle.plate_number)
    ).scalars().all()

    return VehicleListOut(
        total=total,
        items=[VehicleOut.model_validate(v) for v in vehicles],
    )


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    body: VehicleCreate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Register a new vehicle."""
    # Check for duplicate plate
    existing = db.execute(
        select(Vehicle).where(
            Vehicle.plate_normalized == normalize_plate(body.plate_number)
        )
    ).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Vehicle with plate {body.plate_number!r} already registered",
        )

    # Validate owner_person_id if provided
    if body.owner_person_id:
        person = db.get(CampusPerson, body.owner_person_id)
        if not person:
            raise HTTPException(
                status_code=404,
                detail=f"Campus person with ID {body.owner_person_id} not found",
            )
        if not body.owner_name:
            body.owner_name = person.full_name

    vehicle = Vehicle(
        **body.model_dump(exclude={"plate_number"}),
        plate_number=body.plate_number,
        plate_normalized=normalize_plate(body.plate_number),
        registered_by=account.id,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    logger.info("Vehicle created: id=%s plate=%r by=%s", vehicle.id, vehicle.plate_number, account.id)
    return VehicleOut.model_validate(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(
    vehicle_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(get_active_account)],
):
    """Get a vehicle by ID."""
    return VehicleOut.model_validate(_get_vehicle_or_404(vehicle_id, db))


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Update a vehicle's information."""
    vehicle = _get_vehicle_or_404(vehicle_id, db)
    updates = body.model_dump(exclude_unset=True)

    # Validate owner_person_id if provided/updated
    if "owner_person_id" in updates and updates["owner_person_id"] is not None:
        person = db.get(CampusPerson, updates["owner_person_id"])
        if not person:
            raise HTTPException(
                status_code=404,
                detail=f"Campus person with ID {updates['owner_person_id']} not found",
            )
        if not updates.get("owner_name") and not vehicle.owner_name:
            updates["owner_name"] = person.full_name

    # If plate_number is being updated, recompute normalized
    if "plate_number" in updates and updates["plate_number"]:
        updates["plate_normalized"] = normalize_plate(updates["plate_number"])

    for field, value in updates.items():
        setattr(vehicle, field, value)

    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Delete a registered vehicle."""
    vehicle = _get_vehicle_or_404(vehicle_id, db)
    db.delete(vehicle)
    db.commit()
    logger.info("Vehicle deleted: id=%s by=%s", vehicle_id, account.id)
