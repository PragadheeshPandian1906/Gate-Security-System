"""
SmartGuard AI — Access Decision API Routes (Phase 3)

POST /api/access/attempts          — create + evaluate an access attempt
GET  /api/access/attempts          — list access history (paginated)
GET  /api/access/attempts/{id}     — retrieve one attempt with full detail
GET  /api/access/pending-reviews   — list unresolved MANUAL_REVIEW attempts
POST /api/access/attempts/{id}/resolve — resolve a manual review
"""
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_security, require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.access import AccessAttempt
from app.schemas.access import (
    AccessAttemptCreate,
    AccessAttemptResponse,
    AccessAttemptSummary,
    ManualReviewResolve,
)
from app.services.access_decision_service import evaluate_access_attempt, resolve_manual_review

logger = logging.getLogger("smartguard.access")
router = APIRouter(prefix="/access", tags=["access"])


@router.post("/attempts", response_model=AccessAttemptResponse, status_code=status.HTTP_201_CREATED)
def create_access_attempt(
    body: AccessAttemptCreate,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Submit a new access attempt.

    The body must contain IDs of recently persisted face_verification and
    alpr_verification records (created within the last 2 minutes).
    The backend re-validates all data server-side; frontend-supplied
    identity or vehicle claims are ignored.
    """
    result = evaluate_access_attempt(
        db=db,
        direction=body.direction,
        face_verification_id=body.face_verification_id,
        alpr_verification_id=body.alpr_verification_id,
        initiated_by=str(account.id),
    )
    logger.info(
        "access Attempt created: id=%s direction=%s decision=%s by=%s",
        result["attempt_id"], body.direction, result["decision"], account.id,
    )
    return AccessAttemptResponse(**result)


@router.get("/attempts", response_model=list[AccessAttemptSummary])
def list_access_attempts(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    direction: str | None = Query(default=None),
    decision: str | None = Query(default=None),
):
    """List access attempt history, newest first."""
    stmt = select(AccessAttempt).order_by(AccessAttempt.timestamp.desc()).offset(skip).limit(limit)
    if direction:
        stmt = stmt.where(AccessAttempt.direction == direction.upper())
    if decision:
        stmt = stmt.where(AccessAttempt.decision == decision.upper())
    rows = db.execute(stmt).scalars().all()
    return [_to_summary(r) for r in rows]


@router.get("/attempts/{attempt_id}", response_model=AccessAttemptSummary)
def get_access_attempt(
    attempt_id: str,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Retrieve a single access attempt by ID."""
    try:
        uid = uuid.UUID(attempt_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attempt ID format.")

    row = db.execute(
        select(AccessAttempt).where(AccessAttempt.id == uid)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Access attempt not found.")
    return _to_summary(row)


@router.get("/pending-reviews", response_model=list[AccessAttemptSummary])
def list_pending_reviews(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    limit: int = Query(default=50, ge=1, le=200),
):
    """List all unresolved MANUAL_REVIEW attempts (newest first)."""
    rows = db.execute(
        select(AccessAttempt)
        .where(
            AccessAttempt.review_required == True,  # noqa: E712
            AccessAttempt.review_resolved == False,  # noqa: E712
        )
        .order_by(AccessAttempt.timestamp.desc())
        .limit(limit)
    ).scalars().all()
    return [_to_summary(r) for r in rows]


@router.post("/attempts/{attempt_id}/resolve")
def resolve_attempt(
    attempt_id: str,
    body: ManualReviewResolve,
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Resolve a pending manual-review attempt.
    Requires a mandatory reason. Re-validates eligibility before approving.
    Cannot resolve the same attempt twice.
    """
    result = resolve_manual_review(
        db=db,
        attempt_id=attempt_id,
        resolution=body.resolution,
        reason=body.reason,
        reviewed_by=str(account.id),
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    logger.info(
        "access Manual review resolved: attempt=%s resolution=%s by=%s",
        attempt_id, body.resolution, account.id,
    )
    return result


def _to_summary(row: AccessAttempt) -> AccessAttemptSummary:
    import json
    codes = row.reason_codes
    if isinstance(codes, str):
        try:
            codes = json.loads(codes)
        except Exception:
            codes = []
    return AccessAttemptSummary(
        id=str(row.id),
        timestamp=row.timestamp,
        direction=row.direction,
        decision=row.decision,
        gate_result=row.gate_result,
        reason_codes=codes or [],
        reason_text=row.reason_text,
        detected_plate=row.detected_plate,
        matched_person_id=str(row.matched_person_id) if row.matched_person_id else None,
        matched_vehicle_id=str(row.matched_vehicle_id) if row.matched_vehicle_id else None,
        person_status=row.person_status,
        vehicle_status=row.vehicle_status,
        ownership_ok=row.ownership_ok,
        schedule_ok=row.schedule_ok,
        watchlist_hit=row.watchlist_hit,
        watchlist_severity=row.watchlist_severity,
        review_required=row.review_required,
        review_resolved=row.review_resolved,
        review_resolution=row.review_resolution,
        review_reason=row.review_reason,
        reviewed_by=str(row.reviewed_by) if row.reviewed_by else None,
        reviewed_at=row.reviewed_at,
        initiated_by=str(row.initiated_by) if row.initiated_by else None,
        processing_ms=row.processing_ms,
    )
