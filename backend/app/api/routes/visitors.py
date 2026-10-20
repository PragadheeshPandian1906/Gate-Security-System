"""
SmartGuard AI — Phase 5 Visitor Management API Routes

Endpoints:
  - Visitor Identity:
      POST /api/visitors/register          - register/update visitor
      GET  /api/visitors                   - search & list visitors
      GET  /api/visitors/{id}              - visitor detail with history
  - Pass Management:
      POST /api/visitors/passes            - issue new visitor pass + QR + email
      GET  /api/visitors/passes            - list/filter passes
      GET  /api/visitors/passes/metrics    - dashboard metrics
      GET  /api/visitors/passes/{id}       - pass details
      POST /api/visitors/passes/{id}/revoke - revoke pass
      POST /api/visitors/passes/{id}/resend-email - resend pass email
  - Gate QR Scanning & Approval:
      POST /api/visitors/scan              - scan QR pass for ENTRY or EXIT
      GET  /api/visitors/approvals/pending - list pending entry approvals
      POST /api/visitors/approvals/{id}/approve - approve visitor entry
      POST /api/visitors/approvals/{id}/deny    - deny visitor entry
  - Campus Presence:
      GET  /api/visitors/active-inside     - list visitors currently inside campus
"""
import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

logger = logging.getLogger("smartguard.visitors")

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_security
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.people import CampusPerson, Vehicle
from app.models.visitors import VisitorApproval, VisitorPass
from app.schemas.visitors import (
    ActiveVisitorResponse,
    VisitorApprovalDecisionRequest,
    VisitorApprovalResponse,
    VisitorMetricsResponse,
    VisitorPassCreateRequest,
    VisitorPassResponse,
    VisitorPassRevokeRequest,
    VisitorPassSummary,
    VisitorRegistrationRequest,
    VisitorResponse,
    VisitorScanRequest,
    VisitorScanResult,
)
from app.services import visitor_service

router = APIRouter(prefix="/visitors", tags=["visitors"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pass_to_response(vpass: VisitorPass, db: Session, qr_base64: Optional[str] = None) -> VisitorPassResponse:
    visitor = db.get(CampusPerson, vpass.visitor_id)
    host = db.get(CampusPerson, vpass.host_person_id) if vpass.host_person_id else None
    issuer = db.get(SecurityAccount, vpass.issued_by) if vpass.issued_by else None

    # Check validity expiry dynamically
    st = vpass.status
    if st == "ISSUED" and vpass.valid_until < datetime.now(timezone.utc):
        st = "EXPIRED"

    # Always ensure QR code base64 is available for frontend display & printing
    if not qr_base64:
        if vpass.qr_code_path and os.path.exists(vpass.qr_code_path):
            try:
                with open(vpass.qr_code_path, "rb") as f:
                    qr_base64 = base64.b64encode(f.read()).decode("ascii")
            except Exception:
                pass
        if not qr_base64:
            try:
                png_bytes = visitor_service.render_qr_image_bytes(f"SGVP:{vpass.pass_number}")
                qr_base64 = base64.b64encode(png_bytes).decode("ascii")
            except Exception:
                pass

    return VisitorPassResponse(
        id=str(vpass.id),
        pass_number=vpass.pass_number,
        visitor_id=str(vpass.visitor_id),
        visitor_name=visitor.full_name if visitor else "Unknown Visitor",
        visitor_email=visitor.email if visitor else None,
        visitor_phone=visitor.phone if visitor else None,
        host_person_id=str(vpass.host_person_id) if vpass.host_person_id else None,
        host_name=host.full_name if host else None,
        vehicle_id=str(vpass.vehicle_id) if vpass.vehicle_id else None,
        vehicle_plate=vpass.vehicle_plate,
        purpose=vpass.purpose,
        organization=vpass.organization,
        id_type=vpass.id_type,
        id_number=vpass.id_number,
        valid_from=vpass.valid_from,
        valid_until=vpass.valid_until,
        status=st,
        qr_code_path=vpass.qr_code_path,
        qr_code_base64=qr_base64,
        qr_image_base64=qr_base64,
        issued_at=vpass.issued_at,
        issued_by_name=issuer.username if issuer else None,
        check_in_at=vpass.check_in_at,
        check_out_at=vpass.check_out_at,
        revoked_at=vpass.revoked_at,
        revocation_reason=vpass.revocation_reason,
    )


def _approval_to_response(apprv: VisitorApproval, db: Session) -> VisitorApprovalResponse:
    vpass = db.get(VisitorPass, apprv.pass_id)
    visitor = db.get(CampusPerson, apprv.visitor_id)
    host = db.get(CampusPerson, vpass.host_person_id) if (vpass and vpass.host_person_id) else None
    scanner = db.get(SecurityAccount, apprv.scanned_by) if apprv.scanned_by else None
    decider = db.get(SecurityAccount, apprv.decision_by) if apprv.decision_by else None

    return VisitorApprovalResponse(
        id=str(apprv.id),
        pass_id=str(apprv.pass_id),
        pass_number=vpass.pass_number if vpass else "Unknown",
        visitor_id=str(apprv.visitor_id),
        visitor_name=visitor.full_name if visitor else "Unknown",
        host_name=host.full_name if host else None,
        vehicle_plate=vpass.vehicle_plate if vpass else None,
        purpose=vpass.purpose if vpass else "Visit",
        direction=apprv.direction,
        status=apprv.status,
        scanned_at=apprv.scanned_at,
        scanned_by_name=scanner.username if scanner else None,
        decision_by_name=decider.username if decider else None,
        decision_at=apprv.decision_at,
        denial_reason=apprv.denial_reason,
        notes=apprv.notes,
        valid_from=vpass.valid_from if vpass else apprv.scanned_at,
        valid_until=vpass.valid_until if vpass else apprv.scanned_at,
    )


# ---------------------------------------------------------------------------
# 1. Visitor Identity Endpoints
# ---------------------------------------------------------------------------
@router.post("/register", response_model=VisitorResponse, status_code=status.HTTP_201_CREATED)
def register_visitor(
    payload: VisitorRegistrationRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Register or update a visitor identity (stored in campus_people with person_type='visitor')."""
    visitor = visitor_service.register_or_update_visitor(
        db,
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        organization=payload.organization,
        id_type=payload.id_type,
        id_number=payload.id_number,
        notes=payload.notes,
        registered_by=current_account.id,
    )
    db.commit()
    db.refresh(visitor)

    return VisitorResponse(
        id=str(visitor.id),
        full_name=visitor.full_name,
        person_type=visitor.person_type,
        phone=visitor.phone,
        email=visitor.email,
        department=visitor.department,
        status=visitor.status,
        notes=visitor.notes,
        created_at=visitor.created_at,
        updated_at=visitor.updated_at,
        total_visits=0,
    )


@router.get("/people", response_model=List[VisitorResponse])
@router.get("", response_model=List[VisitorResponse])
def list_visitors(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    search: Optional[str] = Query(None, description="Search by name, email, phone, or organization"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List registered visitors with their visit counts and latest pass status."""
    stmt = select(CampusPerson).where(CampusPerson.person_type == "visitor")
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                CampusPerson.full_name.ilike(term),
                CampusPerson.email.ilike(term),
                CampusPerson.phone.ilike(term),
                CampusPerson.department.ilike(term),
            )
        )
    stmt = stmt.order_by(CampusPerson.created_at.desc()).offset(offset).limit(limit)
    visitors = db.execute(stmt).scalars().all()

    results = []
    now = datetime.now(timezone.utc)
    for v in visitors:
        # Total visits
        visit_count = db.execute(
            select(func.count()).select_from(VisitorPass).where(VisitorPass.visitor_id == v.id)
        ).scalar() or 0

        # Latest active pass if any
        latest_pass = db.execute(
            select(VisitorPass).where(
                VisitorPass.visitor_id == v.id,
                VisitorPass.status.in_(["ISSUED", "PENDING_APPROVAL", "ACTIVE_INSIDE"]),
                VisitorPass.valid_until >= now,
            ).order_by(VisitorPass.valid_until.desc())
        ).scalar_one_or_none()

        active_summary = None
        if latest_pass:
            active_summary = VisitorPassSummary(
                id=str(latest_pass.id),
                pass_number=latest_pass.pass_number,
                status=latest_pass.status,
                valid_from=latest_pass.valid_from,
                valid_until=latest_pass.valid_until,
                purpose=latest_pass.purpose,
            )

        results.append(
            VisitorResponse(
                id=str(v.id),
                full_name=v.full_name,
                person_type=v.person_type,
                phone=v.phone,
                email=v.email,
                department=v.department,
                status=v.status,
                notes=v.notes,
                created_at=v.created_at,
                updated_at=v.updated_at,
                total_visits=int(visit_count),
                active_pass=active_summary,
            )
        )
    return results


@router.get("/people/{id}", response_model=VisitorResponse)
def get_visitor(
    id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Retrieve visitor profile."""
    visitor = db.get(CampusPerson, id)
    if not visitor or visitor.person_type != "visitor":
        raise HTTPException(status_code=404, detail="Visitor not found")

    visit_count = db.execute(
        select(func.count()).select_from(VisitorPass).where(VisitorPass.visitor_id == visitor.id)
    ).scalar() or 0

    return VisitorResponse(
        id=str(visitor.id),
        full_name=visitor.full_name,
        person_type=visitor.person_type,
        phone=visitor.phone,
        email=visitor.email,
        department=visitor.department,
        status=visitor.status,
        notes=visitor.notes,
        created_at=visitor.created_at,
        updated_at=visitor.updated_at,
        total_visits=int(visit_count),
    )


# ---------------------------------------------------------------------------
# 2. Pass Management Endpoints
# ---------------------------------------------------------------------------
@router.post("/passes", response_model=VisitorPassResponse, status_code=status.HTTP_201_CREATED)
def issue_pass(
    payload: VisitorPassCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Issue a new temporary visitor pass, generate QR code image, and dispatch email."""
    try:
        vis_uuid = uuid.UUID(str(payload.visitor_id)) if payload.visitor_id else None
        host_uuid = uuid.UUID(str(payload.host_person_id)) if payload.host_person_id else None
        veh_uuid = uuid.UUID(str(payload.vehicle_id)) if payload.vehicle_id else None

        vpass, raw_token, qr_b64 = visitor_service.create_visitor_pass(
            db,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            purpose=payload.purpose,
            visitor_id=vis_uuid,
            full_name=payload.full_name,
            phone=payload.phone,
            email=payload.email,
            host_person_id=host_uuid,
            vehicle_id=veh_uuid,
            vehicle_plate=payload.vehicle_plate,
            organization=payload.organization,
            id_type=payload.id_type,
            id_number=payload.id_number,
            issued_by=current_account.id,
            send_email=payload.send_email,
        )
        return _pass_to_response(vpass, db, qr_base64=qr_b64)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to issue visitor pass: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to issue visitor pass: {str(exc)}")


@router.get("/passes/metrics", response_model=VisitorMetricsResponse)
def get_metrics(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return live metrics for visitor management dashboard."""
    return visitor_service.get_visitor_metrics(db)


@router.get("/passes", response_model=List[VisitorPassResponse])
def list_passes(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List visitor passes with optional status and search filtering."""
    stmt = select(VisitorPass)
    if status_filter and status_filter.strip():
        stmt = stmt.where(VisitorPass.status == status_filter.strip().upper())
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.join(CampusPerson, VisitorPass.visitor_id == CampusPerson.id).where(
            or_(
                VisitorPass.pass_number.ilike(term),
                VisitorPass.vehicle_plate.ilike(term),
                CampusPerson.full_name.ilike(term),
                CampusPerson.email.ilike(term),
            )
        )
    stmt = stmt.order_by(VisitorPass.created_at.desc()).offset(offset).limit(limit)
    passes = db.execute(stmt).scalars().all()
    return [_pass_to_response(p, db) for p in passes]


@router.get("/passes/pending-approvals", response_model=List[VisitorApprovalResponse])
@router.get("/approvals/pending", response_model=List[VisitorApprovalResponse])
def list_pending_approvals(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """List all pending visitor entry approval requests for on-duty security officers."""
    stmt = (
        select(VisitorApproval)
        .where(VisitorApproval.status == "PENDING")
        .order_by(VisitorApproval.scanned_at.desc())
    )
    approvals = db.execute(stmt).scalars().all()
    return [_approval_to_response(a, db) for a in approvals]


@router.get("/passes/active-inside", response_model=List[ActiveVisitorResponse])
@router.get("/active-inside", response_model=List[ActiveVisitorResponse])
def list_active_visitors(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """List visitors currently inside campus."""
    stmt = (
        select(VisitorPass)
        .where(VisitorPass.status == "ACTIVE_INSIDE")
        .order_by(VisitorPass.check_in_at.desc())
    )
    passes = db.execute(stmt).scalars().all()

    now = datetime.now(timezone.utc)
    results = []
    for p in passes:
        visitor = db.get(CampusPerson, p.visitor_id)
        host = db.get(CampusPerson, p.host_person_id) if p.host_person_id else None

        duration = 0
        if p.check_in_at:
            duration = int((now - p.check_in_at).total_seconds() // 60)

        results.append(
            ActiveVisitorResponse(
                pass_id=str(p.id),
                pass_number=p.pass_number,
                visitor_id=str(p.visitor_id),
                visitor_name=visitor.full_name if visitor else "Unknown Visitor",
                visitor_email=visitor.email if visitor else None,
                visitor_phone=visitor.phone if visitor else None,
                host_name=host.full_name if host else "None",
                vehicle_plate=p.vehicle_plate,
                purpose=p.purpose,
                organization=p.organization,
                check_in_at=p.check_in_at or p.issued_at,
                valid_until=p.valid_until,
                duration_minutes=duration,
            )
        )
    return results


@router.get("/passes/{id}", response_model=VisitorPassResponse)
def get_pass_detail(
    id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Retrieve pass details."""
    vpass = db.get(VisitorPass, id)
    if not vpass:
        raise HTTPException(status_code=404, detail="Visitor pass not found")
    return _pass_to_response(vpass, db)


@router.post("/passes/{id}/revoke", response_model=VisitorPassResponse)
def revoke_pass(
    id: uuid.UUID,
    payload: VisitorPassRevokeRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Revoke an active or issued visitor pass."""
    try:
        vpass = visitor_service.revoke_visitor_pass(
            db,
            pass_id=id,
            officer_id=current_account.id,
            reason=payload.reason,
        )
        return _pass_to_response(vpass, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/passes/{id}/resend-email")
def resend_email(
    id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Resend QR pass email to visitor."""
    try:
        status_res = visitor_service.resend_visitor_pass_email(db, pass_id=id)
        return {"status": status_res, "message": f"Pass email delivery status: {status_res}"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# 3. QR Scanning & Approvals Endpoints
# ---------------------------------------------------------------------------
@router.post("/scan", response_model=VisitorScanResult)
def scan_pass(
    payload: VisitorScanRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Validate scanned QR credential from browser camera feed.
    - If ENTRY: creates PENDING approval request (GATE STAYS CLOSED).
    - If EXIT: completes visit and opens gate if inside campus.
    """
    result = visitor_service.scan_and_verify_pass(
        db,
        qr_credential=payload.qr_credential,
        direction=payload.direction,
        scanned_by=current_account.id,
    )
    return VisitorScanResult(**result)


@router.post("/approvals/{id}/decision", response_model=VisitorPassResponse)
def decide_approval(
    id: uuid.UUID,
    payload: VisitorApprovalDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Unified endpoint for approving or denying visitor entry."""
    decision = (payload.decision or "APPROVE").upper()
    if decision == "DENY":
        return deny_entry(id=id, payload=payload, db=db, current_account=current_account)
    return approve_entry(id=id, payload=payload, db=db, current_account=current_account)


@router.post("/approvals/{id}/approve", response_model=VisitorPassResponse)
def approve_entry(
    id: uuid.UUID,
    payload: VisitorApprovalDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Explicitly approve visitor entry:
    - Atomically updates pass to ACTIVE_INSIDE
    - Records exactly one AccessAttempt row
    - Actuates gate barrier via gate_service
    - Resolves related SecurityAlert
    """
    try:
        vpass, _ = visitor_service.approve_visitor_entry(
            db,
            approval_id=id,
            officer_id=current_account.id,
            notes=payload.notes,
        )
        return _pass_to_response(vpass, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/approvals/{id}/deny", response_model=VisitorPassResponse)
def deny_entry(
    id: uuid.UUID,
    payload: VisitorApprovalDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    current_account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Explicitly deny visitor entry:
    - Marks approval DENIED
    - Gate remains CLOSED
    - Records AccessAttempt as DENY
    """
    try:
        reason = payload.denial_reason or "Denied by security officer"
        vpass, _ = visitor_service.deny_visitor_entry(
            db,
            approval_id=id,
            officer_id=current_account.id,
            denial_reason=reason,
            notes=payload.notes,
        )
        return _pass_to_response(vpass, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
