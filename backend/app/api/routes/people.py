"""
SmartGuard AI — Campus People API (Phase 2)

Endpoints:
  GET    /api/people              - list people (paginated, filterable)
  POST   /api/people              - create person
  GET    /api/people/{id}         - get person detail
  PATCH  /api/people/{id}         - update person
  DELETE /api/people/{id}         - delete person
  POST   /api/people/{id}/photo   - upload primary photo
  POST   /api/people/{id}/enroll-face  - enroll face embedding
  GET    /api/people/{id}/faces   - list face profiles for person
"""
import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_admin, require_security
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.people import CampusPerson, FaceProfile
from app.schemas.people import (
    CampusPersonCreate,
    CampusPersonListOut,
    CampusPersonOut,
    CampusPersonUpdate,
    FaceProfileOut,
)
from app.services import storage_service, face_service
from app.services.alpr_service import normalize_plate

logger = logging.getLogger("smartguard.people")
router = APIRouter(prefix="/people", tags=["people"])

# Max upload size: 10 MB
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person_to_out(person: CampusPerson, db: Session) -> CampusPersonOut:
    face_count = db.execute(
        text("SELECT COUNT(*) FROM face_profiles WHERE person_id = :pid"),
        {"pid": str(person.id)},
    ).scalar() or 0
    data = CampusPersonOut.model_validate(person)
    data.face_profile_count = int(face_count)
    return data


def _get_person_or_404(person_id: uuid.UUID, db: Session) -> CampusPerson:
    person = db.get(CampusPerson, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=CampusPersonListOut)
def list_people(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(get_active_account)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    person_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    """List campus people with optional filters and pagination."""
    q = select(CampusPerson)
    if person_type:
        q = q.where(CampusPerson.person_type == person_type)
    if status:
        q = q.where(CampusPerson.status == status)
    if search:
        pattern = f"%{search}%"
        q = q.where(
            (CampusPerson.full_name.ilike(pattern))
            | (CampusPerson.employee_id.ilike(pattern))
            | (CampusPerson.email.ilike(pattern))
        )

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    people = db.execute(q.offset(skip).limit(limit).order_by(CampusPerson.full_name)).scalars().all()

    return CampusPersonListOut(
        total=total,
        items=[_person_to_out(p, db) for p in people],
    )


@router.post("", response_model=CampusPersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    body: CampusPersonCreate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Register a new campus person."""
    person = CampusPerson(
        **body.model_dump(),
        registered_by=account.id,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    logger.info("Person created: id=%s name=%r by=%s", person.id, person.full_name, account.id)
    return _person_to_out(person, db)


@router.get("/{person_id}", response_model=CampusPersonOut)
def get_person(
    person_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(get_active_account)],
):
    """Get a campus person by ID."""
    return _person_to_out(_get_person_or_404(person_id, db), db)


@router.patch("/{person_id}", response_model=CampusPersonOut)
def update_person(
    person_id: uuid.UUID,
    body: CampusPersonUpdate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Update a campus person's information."""
    person = _get_person_or_404(person_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return _person_to_out(person, db)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Delete a campus person and all associated face profiles."""
    person = _get_person_or_404(person_id, db)
    db.delete(person)
    db.commit()
    logger.info("Person deleted: id=%s by=%s", person_id, account.id)


@router.post("/{person_id}/photo", response_model=dict)
async def upload_photo(
    person_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """Upload a primary photo for a campus person."""
    person = _get_person_or_404(person_id, db)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {sorted(ALLOWED_IMAGE_TYPES)}",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"{person_id}_photo.{ext}"

    result = storage_service.save_file(
        data=data,
        bucket="face-images",
        subfolder="photos",
        filename=filename,
        content_type=file.content_type or "image/jpeg",
    )

    person.photo_path = result.local_path
    person.photo_storage_path = result.storage_path
    db.commit()

    return {
        "message": "Photo uploaded successfully",
        "local_path": result.local_path,
        "storage_path": result.storage_path,
        "local_ok": result.local_ok,
        "remote_ok": result.remote_ok,
    }


@router.post("/{person_id}/enroll-face", response_model=dict)
async def enroll_face(
    person_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_admin)],
):
    """
    Enroll a face for a campus person.
    Extracts ArcFace embedding and stores in face_profiles with pgvector.
    """
    person = _get_person_or_404(person_id, db)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"{person_id}_face_{uuid.uuid4().hex[:8]}.{ext}"

    storage_result = storage_service.save_file(
        data=data,
        bucket="face-images",
        subfolder="enrollments",
        filename=filename,
        content_type=file.content_type or "image/jpeg",
    )

    enroll_result = face_service.enroll_face(
        person_id=str(person_id),
        image_bytes=data,
        db=db,
        enrolled_by_id=str(account.id),
        image_local_path=storage_result.local_path,
        image_storage_path=storage_result.storage_path,
    )

    if not enroll_result["success"]:
        raise HTTPException(
            status_code=422,
            detail=enroll_result.get("error", "Face enrollment failed"),
        )

    return {
        "message": "Face enrolled successfully",
        "profile_id": enroll_result["profile_id"],
        "faces_detected": enroll_result["faces_detected"],
        "storage": storage_result.to_dict(),
    }


@router.get("/{person_id}/faces", response_model=list[FaceProfileOut])
def list_face_profiles(
    person_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(get_active_account)],
):
    """List face profiles (embeddings) for a campus person."""
    _get_person_or_404(person_id, db)
    profiles = db.execute(
        select(FaceProfile).where(FaceProfile.person_id == person_id)
    ).scalars().all()
    return [FaceProfileOut.model_validate(p) for p in profiles]
