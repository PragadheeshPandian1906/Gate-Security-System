"""
SmartGuard AI — Phase 5 Visitor Management Service

Orchestrates:
  - Visitor identity registration (CampusPerson where person_type='visitor')
  - Cryptographically secure QR pass creation and SHA-256 token hashing
  - Dual-storage QR image generation (local disk + private Supabase bucket)
  - Phase 4 email notification integration with branding & delivery logs
  - Scanned QR credential verification against lifecycle, validity windows, and schedules
  - Mandatory security officer approval workflow (safe atomic state transitions)
  - Visitor entry & exit tracking with single AccessAttempt event persistence
  - Hardware-authoritative simulated gate actuation (gate_service)
"""
import base64
import hashlib
import io
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import qrcode
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.account import SecurityAccount
from app.models.access import AccessAttempt
from app.models.alerts import NotificationLog, SecurityAlert
from app.models.people import CampusPerson, Vehicle
from app.models.visitors import VisitorApproval, VisitorPass
from app.services import email_service, gate_service, schedule_service, storage_service

logger = logging.getLogger("smartguard.visitor_service")


# ---------------------------------------------------------------------------
# Helper: Generate High-Entropy Cryptographic Token & Hash
# ---------------------------------------------------------------------------
def generate_qr_credential() -> Tuple[str, str]:
    """
    Generate a high-entropy random URL-safe token (32 bytes = 256 bits entropy)
    and compute its SHA-256 hex digest.

    Returns:
        (raw_token, token_hash)
        NOTE: raw_token is ONLY returned to be encoded into the QR code image.
        It is NEVER stored in the database.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of a scanned token string."""
    cleaned = raw_token.strip()
    if cleaned.startswith("SGVP:"):
        cleaned = cleaned[5:]
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def generate_pass_number() -> str:
    """Generate a clean human-readable pass reference e.g. VP-20261018-7F3A2C."""
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_suffix = secrets.token_hex(3).upper()
    return f"VP-{today_str}-{random_suffix}"


def render_qr_image_bytes(payload: str) -> bytes:
    """Render a high-contrast QR code as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Visitor Identity Management
# ---------------------------------------------------------------------------
def register_or_update_visitor(
    db: Session,
    full_name: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    organization: Optional[str] = None,
    id_type: Optional[str] = None,
    id_number: Optional[str] = None,
    notes: Optional[str] = None,
    registered_by: Optional[uuid.UUID] = None,
) -> CampusPerson:
    """
    Find existing visitor identity by email or phone (to prevent duplicates),
    or create a new CampusPerson entity with person_type='visitor'.
    """
    visitor = None

    # Search for existing visitor by email or phone
    if email and email.strip():
        visitor = db.execute(
            select(CampusPerson).where(
                CampusPerson.person_type == "visitor",
                func.lower(CampusPerson.email) == email.strip().lower(),
            )
        ).scalar_one_or_none()

    if not visitor and phone and phone.strip():
        visitor = db.execute(
            select(CampusPerson).where(
                CampusPerson.person_type == "visitor",
                CampusPerson.phone == phone.strip(),
            )
        ).scalar_one_or_none()

    if visitor:
        # Update contact / organization details if changed
        visitor.full_name = full_name.strip()
        if phone:
            visitor.phone = phone.strip()
        if email:
            visitor.email = email.strip().lower()
        if organization:
            visitor.department = organization.strip()
        if notes:
            visitor.notes = notes.strip()
        db.flush()
        return visitor

    # Create new visitor
    visitor = CampusPerson(
        id=uuid.uuid4(),
        full_name=full_name.strip(),
        person_type="visitor",
        phone=phone.strip() if phone else None,
        email=email.strip().lower() if email else None,
        department=organization.strip() if organization else None,
        employee_id=id_number.strip() if id_number else None,
        notes=notes.strip() if notes else None,
        status="active",
        registered_by=registered_by,
    )
    db.add(visitor)
    db.flush()
    return visitor


# ---------------------------------------------------------------------------
# Pass Creation & Email Dispatch
# ---------------------------------------------------------------------------
def create_visitor_pass(
    db: Session,
    valid_from: datetime,
    valid_until: datetime,
    purpose: str = "Campus Meeting",
    visitor_id: Optional[uuid.UUID] = None,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    host_person_id: Optional[uuid.UUID] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    vehicle_plate: Optional[str] = None,
    organization: Optional[str] = None,
    id_type: Optional[str] = None,
    id_number: Optional[str] = None,
    issued_by: Optional[uuid.UUID] = None,
    send_email: bool = True,
) -> Tuple[VisitorPass, str, str]:
    """
    Create a new visitor pass, generate QR code image, store it via dual storage,
    and optionally dispatch a notification email.

    Returns:
        (VisitorPass, raw_token, qr_base64)
    """
    # Validate validity period
    if valid_until <= valid_from:
        raise ValueError("Pass valid_until timestamp must be after valid_from")

    # Resolve visitor
    if visitor_id:
        visitor = db.get(CampusPerson, visitor_id)
        if not visitor:
            raise ValueError(f"Visitor with ID {visitor_id} not found")
    else:
        if not full_name or not full_name.strip():
            raise ValueError("Visitor full_name is required when visitor_id is omitted")
        visitor = register_or_update_visitor(
            db,
            full_name=full_name,
            phone=phone,
            email=email,
            organization=organization,
            id_type=id_type,
            id_number=id_number,
            registered_by=issued_by,
        )

    # Clean license plate if provided
    norm_plate = None
    if vehicle_plate and vehicle_plate.strip():
        norm_plate = vehicle_plate.strip().upper().replace(" ", "")

    pass_number = generate_pass_number()
    raw_token, token_hash = generate_qr_credential()

    # The payload placed inside the QR image
    qr_payload = f"SGVP:{raw_token}"
    qr_png_bytes = render_qr_image_bytes(qr_payload)
    qr_base64 = base64.b64encode(qr_png_bytes).decode("ascii")

    # Dual storage save
    storage_res = storage_service.save_file(
        data=qr_png_bytes,
        bucket="visitor-qr",
        filename=f"qr_{pass_number}.png",
        content_type="image/png",
    )

    new_pass = VisitorPass(
        id=uuid.uuid4(),
        pass_number=pass_number,
        visitor_id=visitor.id,
        host_person_id=host_person_id,
        vehicle_id=vehicle_id,
        vehicle_plate=norm_plate,
        purpose=purpose.strip() or "Campus Meeting",
        organization=organization.strip() if organization else visitor.department,
        id_type=id_type.strip() if id_type else None,
        id_number=id_number.strip() if id_number else visitor.employee_id,
        valid_from=valid_from,
        valid_until=valid_until,
        token_hash=token_hash,
        qr_code_path=storage_res.local_path,
        qr_storage_path=storage_res.storage_path,
        status="ISSUED",
        issued_by=issued_by,
    )
    db.add(new_pass)
    db.commit()
    db.refresh(new_pass)

    # Dispatch email if requested and visitor has email
    delivery_status = "NOT_REQUESTED"
    if send_email and visitor.email:
        try:
            delivery_status = dispatch_visitor_pass_email(db, new_pass, visitor, qr_base64)
        except Exception as exc:
            logger.error("dispatch_visitor_pass_email exception: %s", exc, exc_info=True)
            delivery_status = "FAILED"

    return new_pass, raw_token, qr_base64


def dispatch_visitor_pass_email(
    db: Session,
    visitor_pass: VisitorPass,
    visitor: CampusPerson,
    qr_base64: str,
) -> str:
    """
    Format and dispatch the secure QR visitor pass email via Phase 4 email service.
    Records delivery in notification_log.
    """
    if not visitor.email:
        return "NO_EMAIL"

    host_name = "Campus Host"
    if visitor_pass.host_person_id:
        host = db.get(CampusPerson, visitor_pass.host_person_id)
        if host:
            host_name = host.full_name

    # Format timestamps in IST
    import zoneinfo
    try:
        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    except Exception:
        ist = timezone.utc

    vf_ist = visitor_pass.valid_from.astimezone(ist).strftime("%d %b %Y, %I:%M %p IST")
    vu_ist = visitor_pass.valid_until.astimezone(ist).strftime("%d %b %Y, %I:%M %p IST")

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #e2e8f0; margin: 0; padding: 24px; }}
        .card {{ max-width: 540px; margin: 0 auto; background-color: #151c2c; border: 1px solid #2d3748; border-radius: 12px; overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 24px; text-align: center; color: #ffffff; }}
        .content {{ padding: 24px; }}
        .qr-notice {{ text-align: center; background: #1e293b; border: 2px dashed #4f46e5; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .qr-notice p {{ color: #a5b4fc; font-size: 13px; margin: 0; }}
        .qr-notice .pass-num {{ font-family: monospace; font-size: 18px; font-weight: bold; color: #818cf8; margin-top: 8px; }}
        .details {{ background-color: #1e293b; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }}
        .label {{ color: #94a3b8; }}
        .val {{ font-weight: 600; color: #f1f5f9; }}
        .warning {{ font-size: 11px; color: #fbbf24; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.2); padding: 12px; border-radius: 6px; text-align: center; margin-top: 16px; }}
        .footer {{ font-size: 11px; text-align: center; color: #64748b; padding: 16px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h2 style="margin: 0; font-size: 20px;">SmartGuard AI</h2>
          <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Intelligent Campus Gate Security</p>
        </div>
        <div class="content">
          <p style="margin-top: 0;">Dear <strong>{visitor.full_name}</strong>,</p>
          <p>Your temporary campus access pass has been approved and issued. Your <strong>QR code is attached to this email</strong> as a PNG image (<code>{visitor_pass.pass_number}_qr.png</code>). Please save it and present it to the gate security officer upon arrival.</p>

          <div class="qr-notice">
            <p>🔒 QR Pass attached as PNG image</p>
            <div class="pass-num">{visitor_pass.pass_number}</div>
            <p style="margin-top: 8px; font-size: 12px; color: #64748b;">Open the attached file on your phone or print it before visiting.</p>
          </div>

          <div class="details">
            <div class="row"><span class="label">Visitor:</span><span class="val">{visitor.full_name}</span></div>
            <div class="row"><span class="label">Host / Sponsor:</span><span class="val">{host_name}</span></div>
            <div class="row"><span class="label">Purpose:</span><span class="val">{visitor_pass.purpose}</span></div>
            {f'<div class="row"><span class="label">Vehicle:</span><span class="val">{visitor_pass.vehicle_plate}</span></div>' if visitor_pass.vehicle_plate else ''}
            <div class="row"><span class="label">Valid From:</span><span class="val">{vf_ist}</span></div>
            <div class="row"><span class="label">Valid Until:</span><span class="val">{vu_ist}</span></div>
          </div>

          <div class="warning">
            <strong>Mandatory Security Protocol:</strong> Possession of this QR pass does not guarantee immediate physical entry. All visitor entries remain subject to on-duty security officer inspection and explicit verification.
          </div>
        </div>
        <div class="footer">
          SmartGuard AI Automated Perimeter Security &copy; 2026. This is a system-generated credential.
        </div>
      </div>
    </body>
    </html>
    """

    subject = f"[SmartGuard AI] Your Campus Visitor Pass — {visitor_pass.pass_number}"
    idem_key = f"visitor_pass_{visitor_pass.id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

    # Log in notification_log
    notif = NotificationLog(
        id=uuid.uuid4(),
        notification_type="ALERT",
        recipient_email=visitor.email,
        subject=subject,
        status="PENDING",
        attempt_count=0,
        max_attempts=3,
        provider="BREVO" if email_service.is_email_enabled() else "CONSOLE",
        idempotency_key=idem_key,
    )
    db.add(notif)
    db.commit()

    # Attempt dispatch — pass QR as a PNG attachment
    qr_attachment = None
    if qr_base64:
        qr_attachment = [{
            "name": f"{visitor_pass.pass_number}_qr.png",
            "content": qr_base64,
            "content_type": "image/png",
        }]

    try:
        res = email_service.send_email(
            to_address=visitor.email,
            to_name=visitor.full_name or "Visitor",
            subject=subject,
            html_body=html_body,
            attachments=qr_attachment,
        )
        success = bool(res.get("success", False)) if isinstance(res, dict) else False
        provider_id = res.get("provider_message_id") if isinstance(res, dict) else None
        err = res.get("error") if isinstance(res, dict) else None
    except Exception as exc:
        logger.error("email_service unexpected error dispatching to %s: %s", visitor.email, exc, exc_info=True)
        success = False
        provider_id = None
        err = str(exc)

    if success:
        notif.status = "SENT"
        notif.sent_at = datetime.now(timezone.utc)
        notif.provider_message_id = provider_id
        db.commit()
        return "SENT"
    else:
        notif.status = "FAILED"
        notif.error_detail = str(err)[:500] if err else "Email dispatch failed"
        db.commit()
        return "FAILED"


# ---------------------------------------------------------------------------
# QR Scanner & Pass Verification
# ---------------------------------------------------------------------------
def scan_and_verify_pass(
    db: Session,
    qr_credential: str,
    direction: str = "ENTRY",
    scanned_by: Optional[uuid.UUID] = None,
) -> dict:
    """
    Validate a scanned QR pass credential against lifecycle rules and schedules.

    CRITICAL RULES:
      - Valid scan for ENTRY NEVER opens the gate automatically.
        It creates a PENDING VisitorApproval request and a SecurityAlert.
      - Gate stays CLOSED until an authorized officer explicitly approves.
      - Valid scan for EXIT: If visitor is ACTIVE_INSIDE, processes exit and actuates gate.
      - A visitor whose entry window has ended while inside campus CAN still safely exit.
    """
    now = datetime.now(timezone.utc)
    token_h = hash_token(qr_credential)

    # 1. Lookup pass by token hash
    vpass = db.execute(
        select(VisitorPass).where(VisitorPass.token_hash == token_h)
    ).scalar_one_or_none()

    if not vpass:
        logger.warning("visitor_service Invalid QR credential presented token_hash=%s", token_h[:12])
        # Log security alert for invalid credential scan (deduplicated by token prefix)
        _create_invalid_scan_alert(db, token_h)
        return {
            "status": "DENIED",
            "message": "Invalid QR code. No matching visitor pass found in the system.",
            "direction": direction,
            "gate_state": "CLOSED",
        }

    visitor = db.get(CampusPerson, vpass.visitor_id)
    host = db.get(CampusPerson, vpass.host_person_id) if vpass.host_person_id else None
    host_name = host.full_name if host else "None / Unassigned"

    # 2. Check if revoked
    if vpass.status == "REVOKED":
        return {
            "status": "DENIED",
            "message": f"Visitor pass {vpass.pass_number} was revoked: {vpass.revocation_reason or 'No reason provided'}",
            "pass_id": str(vpass.id),
            "pass_number": vpass.pass_number,
            "visitor_name": visitor.full_name if visitor else "Unknown",
            "direction": direction,
            "gate_state": "CLOSED",
        }

    # 3. Check if already completed
    if vpass.status == "COMPLETED" and direction == "ENTRY":
        return {
            "status": "DENIED",
            "message": f"Visitor pass {vpass.pass_number} has already completed its visit and cannot be reused.",
            "pass_id": str(vpass.id),
            "pass_number": vpass.pass_number,
            "visitor_name": visitor.full_name if visitor else "Unknown",
            "direction": direction,
            "gate_state": "CLOSED",
        }

    # 4. Check Schedule
    sched_eval = schedule_service.evaluate_schedule(db)
    sched_ok = sched_eval.get("ok", True)
    schedule_status = "OPEN" if sched_ok else "CLOSED"

    # -----------------------------------------------------------------------
    # ENTRY Workflow: Create Pending Approval (GATE STAYS CLOSED)
    # -----------------------------------------------------------------------
    if direction.upper() == "ENTRY":
        # Check if already inside
        if vpass.status == "ACTIVE_INSIDE":
            return {
                "status": "DENIED",
                "message": f"Visitor {visitor.full_name if visitor else ''} is already recorded as inside campus.",
                "pass_id": str(vpass.id),
                "pass_number": vpass.pass_number,
                "visitor_name": visitor.full_name if visitor else "Unknown",
                "direction": direction,
                "gate_state": "CLOSED",
            }

        # Check validity window
        if now < vpass.valid_from:
            return {
                "status": "DENIED",
                "message": f"Pass is not yet active. Valid from {vpass.valid_from.strftime('%Y-%m-%d %H:%M UTC')}.",
                "pass_id": str(vpass.id),
                "pass_number": vpass.pass_number,
                "visitor_name": visitor.full_name if visitor else "Unknown",
                "direction": direction,
                "gate_state": "CLOSED",
            }

        if now > vpass.valid_until:
            vpass.status = "EXPIRED"
            db.commit()
            return {
                "status": "DENIED",
                "message": f"Pass expired at {vpass.valid_until.strftime('%Y-%m-%d %H:%M UTC')}. New pass required.",
                "pass_id": str(vpass.id),
                "pass_number": vpass.pass_number,
                "visitor_name": visitor.full_name if visitor else "Unknown",
                "direction": direction,
                "gate_state": "CLOSED",
            }

        # Check for existing PENDING approval request to avoid duplicates
        existing_approval = db.execute(
            select(VisitorApproval).where(
                VisitorApproval.pass_id == vpass.id,
                VisitorApproval.status == "PENDING",
            )
        ).scalar_one_or_none()

        if existing_approval:
            approval = existing_approval
        else:
            # Create persistent pending approval request
            approval = VisitorApproval(
                id=uuid.uuid4(),
                pass_id=vpass.id,
                visitor_id=vpass.visitor_id,
                scanned_at=now,
                scanned_by=scanned_by,
                direction="ENTRY",
                status="PENDING",
            )
            vpass.status = "PENDING_APPROVAL"
            db.add(approval)
            db.flush()

            # Create Phase 4 Security Alert
            alert_id = _create_visitor_approval_alert(db, vpass, visitor, host_name, approval.id)
            approval.alert_id = alert_id
            db.commit()

        return {
            "status": "PENDING_APPROVAL",
            "message": f"Pass {vpass.pass_number} is valid. Entry requires explicit security officer authorization.",
            "pass_id": str(vpass.id),
            "pass_number": vpass.pass_number,
            "visitor_name": visitor.full_name if visitor else "Unknown",
            "visitor_email": visitor.email if visitor else None,
            "visitor_phone": visitor.phone if visitor else None,
            "host_name": host_name,
            "vehicle_plate": vpass.vehicle_plate,
            "purpose": vpass.purpose,
            "valid_from": vpass.valid_from,
            "valid_until": vpass.valid_until,
            "direction": "ENTRY",
            "approval_id": str(approval.id),
            "gate_state": "CLOSED",
            "schedule_status": schedule_status,
        }

    # -----------------------------------------------------------------------
    # EXIT Workflow: Process Exit (Can exit even if validity window ended)
    # -----------------------------------------------------------------------
    elif direction.upper() == "EXIT":
        if vpass.status != "ACTIVE_INSIDE":
            return {
                "status": "DENIED",
                "message": f"Pass {vpass.pass_number} is not recorded as inside campus (current status: {vpass.status}).",
                "pass_id": str(vpass.id),
                "pass_number": vpass.pass_number,
                "visitor_name": visitor.full_name if visitor else "Unknown",
                "direction": direction,
                "gate_state": "CLOSED",
            }

        # Complete the visit
        vpass.status = "COMPLETED"
        vpass.check_out_at = now
        vpass.check_out_by = scanned_by

        # Record AccessAttempt
        officer = db.get(SecurityAccount, scanned_by) if scanned_by else None
        officer_name = officer.username if officer else "Security"

        attempt = AccessAttempt(
            id=uuid.uuid4(),
            timestamp=now,
            direction="EXIT",
            decision="ALLOW",
            gate_result="OPEN",
            matched_person_id=visitor.id,
            person_status=visitor.status,
            detected_plate=vpass.vehicle_plate,
            detected_plate_normalized=vpass.vehicle_plate.replace(" ", "").upper() if vpass.vehicle_plate else None,
            matched_vehicle_id=vpass.vehicle_id,
            visitor_pass_id=vpass.id,
            reason_codes=["VISITOR_PASS_EXIT"],
            reason_text=f"Visitor pass {vpass.pass_number} exit processed by {officer_name}",
            initiated_by=scanned_by,
            schedule_ok=sched_ok,
            review_required=False,
            review_resolved=True,
            review_resolution="approved",
            reviewed_by=scanned_by,
            reviewed_at=now,
        )
        db.add(attempt)
        db.commit()

        # Actuate gate
        gate_service.apply_decision("ALLOW", "EXIT", str(attempt.id))

        return {
            "status": "COMPLETED",
            "message": f"Visitor {visitor.full_name if visitor else ''} checked out successfully. Barrier opened.",
            "pass_id": str(vpass.id),
            "pass_number": vpass.pass_number,
            "visitor_name": visitor.full_name if visitor else "Unknown",
            "direction": "EXIT",
            "gate_state": "OPEN",
            "schedule_status": schedule_status,
        }

    return {"status": "ERROR", "message": f"Unsupported direction: {direction}", "direction": direction}


# ---------------------------------------------------------------------------
# Security Officer Decision: Approve or Deny Entry
# ---------------------------------------------------------------------------
def approve_visitor_entry(
    db: Session,
    approval_id: uuid.UUID,
    officer_id: uuid.UUID,
    notes: Optional[str] = None,
) -> Tuple[VisitorPass, AccessAttempt]:
    """
    Explicitly approve a pending visitor entry request.
    Atomic transaction:
      - Marks VisitorApproval APPROVED
      - Transitions VisitorPass to ACTIVE_INSIDE
      - Records check_in_at timestamp and officer attribution
      - Records exactly one AccessAttempt row
      - Actuates gate barrier via gate_service.apply_decision("ALLOW", "ENTRY", attempt_id)
      - Resolves associated SecurityAlert
    """
    now = datetime.now(timezone.utc)

    # Lock approval row for update
    approval = db.execute(
        select(VisitorApproval).where(VisitorApproval.id == approval_id).with_for_update()
    ).scalar_one_or_none()

    if not approval:
        raise ValueError("Approval request not found")

    if approval.status != "PENDING":
        raise ValueError(f"Approval request is already {approval.status}")

    vpass = db.execute(
        select(VisitorPass).where(VisitorPass.id == approval.pass_id).with_for_update()
    ).scalar_one_or_none()

    if not vpass:
        raise ValueError("Associated visitor pass not found")

    if vpass.status in ("REVOKED", "COMPLETED"):
        raise ValueError(f"Cannot approve pass in {vpass.status} status")

    visitor = db.get(CampusPerson, vpass.visitor_id)
    officer = db.get(SecurityAccount, officer_id)
    officer_name = officer.username if officer else "Security Officer"

    # Update approval
    approval.status = "APPROVED"
    approval.decision_by = officer_id
    approval.decision_at = now
    approval.notes = notes

    # Update pass
    vpass.status = "ACTIVE_INSIDE"
    vpass.check_in_at = now
    vpass.check_in_by = officer_id

    # Check schedule
    sched_res = schedule_service.evaluate_schedule(db)
    sched_ok = bool(sched_res.get("ok", True))

    # Persist AccessAttempt
    attempt = AccessAttempt(
        id=uuid.uuid4(),
        timestamp=now,
        direction="ENTRY",
        decision="ALLOW",
        gate_result="OPEN",
        matched_person_id=visitor.id if visitor else None,
        person_status=visitor.status if visitor else "active",
        detected_plate=vpass.vehicle_plate,
        detected_plate_normalized=vpass.vehicle_plate.replace(" ", "").upper() if vpass.vehicle_plate else None,
        matched_vehicle_id=vpass.vehicle_id,
        visitor_pass_id=vpass.id,
        reason_codes=["VISITOR_PASS_ENTRY"],
        reason_text=f"Visitor pass {vpass.pass_number} approved for entry by {officer_name}",
        initiated_by=officer_id,
        schedule_ok=sched_ok,
        review_required=True,
        review_resolved=True,
        review_resolution="approved",
        reviewed_by=officer_id,
        reviewed_at=now,
        review_reason=notes or "Visitor credentials verified by officer",
    )
    db.add(attempt)
    db.flush()

    approval.access_attempt_id = attempt.id

    # Resolve associated alert if exists
    if approval.alert_id:
        alert = db.get(SecurityAlert, approval.alert_id)
        if alert and alert.status in ("OPEN", "ACKNOWLEDGED", "INVESTIGATING"):
            alert.status = "RESOLVED"
            alert.resolved_by = officer_id
            alert.resolved_at = now
            alert.resolution_reason = f"Visitor entry approved by {officer_name}"
            alert.access_attempt_id = attempt.id

    db.commit()

    # Actuate gate
    gate_service.apply_decision("ALLOW", "ENTRY", str(attempt.id))

    logger.info(
        "visitor_service Visitor entry approved pass=%s visitor=%s officer=%s",
        vpass.pass_number, visitor.full_name if visitor else "", officer_name,
    )
    return vpass, attempt


def deny_visitor_entry(
    db: Session,
    approval_id: uuid.UUID,
    officer_id: uuid.UUID,
    denial_reason: str,
    notes: Optional[str] = None,
) -> Tuple[VisitorPass, AccessAttempt]:
    """
    Explicitly deny a pending visitor entry request.
    Gate stays CLOSED. AccessAttempt recorded as DENY.
    """
    now = datetime.now(timezone.utc)

    approval = db.execute(
        select(VisitorApproval).where(VisitorApproval.id == approval_id).with_for_update()
    ).scalar_one_or_none()

    if not approval:
        raise ValueError("Approval request not found")

    if approval.status != "PENDING":
        raise ValueError(f"Approval request is already {approval.status}")

    vpass = db.execute(
        select(VisitorPass).where(VisitorPass.id == approval.pass_id).with_for_update()
    ).scalar_one_or_none()

    if not vpass:
        raise ValueError("Associated visitor pass not found")

    visitor = db.get(CampusPerson, vpass.visitor_id)
    officer = db.get(SecurityAccount, officer_id)
    officer_name = officer.username if officer else "Security Officer"

    approval.status = "DENIED"
    approval.decision_by = officer_id
    approval.decision_at = now
    approval.denial_reason = denial_reason
    approval.notes = notes

    vpass.status = "DENIED"

    # Persist AccessAttempt as DENY
    attempt = AccessAttempt(
        id=uuid.uuid4(),
        timestamp=now,
        direction="ENTRY",
        decision="DENY",
        gate_result="CLOSED",
        matched_person_id=visitor.id if visitor else None,
        person_status=visitor.status if visitor else "active",
        detected_plate=vpass.vehicle_plate,
        detected_plate_normalized=vpass.vehicle_plate.replace(" ", "").upper() if vpass.vehicle_plate else None,
        matched_vehicle_id=vpass.vehicle_id,
        visitor_pass_id=vpass.id,
        reason_codes=["VISITOR_PASS_DENIED"],
        reason_text=f"Visitor pass {vpass.pass_number} entry denied by {officer_name}: {denial_reason}",
        initiated_by=officer_id,
        review_required=True,
        review_resolved=True,
        review_resolution="denied",
        reviewed_by=officer_id,
        reviewed_at=now,
        review_reason=denial_reason,
    )
    db.add(attempt)
    db.flush()

    approval.access_attempt_id = attempt.id

    # Update alert
    if approval.alert_id:
        alert = db.get(SecurityAlert, approval.alert_id)
        if alert and alert.status in ("OPEN", "ACKNOWLEDGED", "INVESTIGATING"):
            alert.status = "RESOLVED"
            alert.resolved_by = officer_id
            alert.resolved_at = now
            alert.resolution_reason = f"Entry denied by officer: {denial_reason}"
            alert.access_attempt_id = attempt.id

    db.commit()

    # Ensure gate is CLOSED
    gate_service.apply_decision("DENY", "ENTRY", str(attempt.id))

    logger.info(
        "visitor_service Visitor entry denied pass=%s visitor=%s reason=%s",
        vpass.pass_number, visitor.full_name if visitor else "", denial_reason,
    )
    return vpass, attempt


# ---------------------------------------------------------------------------
# Pass Revocation & Resend
# ---------------------------------------------------------------------------
def revoke_visitor_pass(
    db: Session,
    pass_id: uuid.UUID,
    officer_id: uuid.UUID,
    reason: str,
) -> VisitorPass:
    """Revoke an eligible pass. Cancel any pending approvals."""
    now = datetime.now(timezone.utc)
    vpass = db.get(VisitorPass, pass_id)
    if not vpass:
        raise ValueError("Visitor pass not found")

    vpass.status = "REVOKED"
    vpass.revoked_at = now
    vpass.revoked_by = officer_id
    vpass.revocation_reason = reason

    # Cancel any pending approvals
    pending = db.execute(
        select(VisitorApproval).where(
            VisitorApproval.pass_id == pass_id,
            VisitorApproval.status == "PENDING",
        )
    ).scalars().all()
    for apprv in pending:
        apprv.status = "CANCELLED"
        apprv.notes = f"Pass revoked: {reason}"

    db.commit()
    db.refresh(vpass)
    return vpass


def resend_visitor_pass_email(db: Session, pass_id: uuid.UUID) -> str:
    """Resend pass email for an eligible pass."""
    vpass = db.get(VisitorPass, pass_id)
    if not vpass:
        raise ValueError("Visitor pass not found")

    if vpass.status in ("REVOKED", "COMPLETED"):
        raise ValueError(f"Cannot resend email for a pass in {vpass.status} state")

    visitor = db.get(CampusPerson, vpass.visitor_id)
    if not visitor or not visitor.email:
        raise ValueError("Visitor does not have an email address configured")

    # Read existing QR image bytes or regenerate from token_hash
    qr_b64 = ""
    if vpass.qr_code_path:
        import os
        if os.path.exists(vpass.qr_code_path):
            with open(vpass.qr_code_path, "rb") as f:
                qr_b64 = base64.b64encode(f.read()).decode("ascii")

    if not qr_b64:
        # Re-render QR placeholder with pass number
        png = render_qr_image_bytes(f"SGVP_REF:{vpass.pass_number}")
        qr_b64 = base64.b64encode(png).decode("ascii")

    return dispatch_visitor_pass_email(db, vpass, visitor, qr_b64)


# ---------------------------------------------------------------------------
# Phase 4 Alert Creation Helpers
# ---------------------------------------------------------------------------
def _create_visitor_approval_alert(
    db: Session,
    vpass: VisitorPass,
    visitor: Optional[CampusPerson],
    host_name: str,
    approval_id: uuid.UUID,
) -> uuid.UUID:
    """Create a SecurityAlert for visitor entry awaiting approval."""
    visitor_name = visitor.full_name if visitor else "Visitor"
    alert_id = uuid.uuid4()
    alert = SecurityAlert(
        id=alert_id,
        category="MANUAL_REVIEW",
        severity="MEDIUM",
        title=f"Visitor Entry Awaiting Approval — {visitor_name} ({vpass.pass_number})",
        description=(
            f"Visitor '{visitor_name}' scanned pass {vpass.pass_number} for ENTRY.\n"
            f"Purpose: {vpass.purpose}\n"
            f"Host: {host_name}\n"
            f"Vehicle: {vpass.vehicle_plate or 'Pedestrian'}\n"
            f"Approval Request ID: {approval_id}"
        ),
        status="OPEN",
        person_id=visitor.id if visitor else None,
        vehicle_id=vpass.vehicle_id,
        detected_plate=vpass.vehicle_plate,
        visitor_pass_id=vpass.id,
    )
    db.add(alert)
    db.flush()
    return alert_id


def _create_invalid_scan_alert(db: Session, token_hash: str) -> None:
    """Create or deduplicate a security alert when an invalid QR is scanned."""
    dedup = f"INVALID_QR_{token_hash[:16]}"
    existing = db.execute(
        select(SecurityAlert).where(
            SecurityAlert.title.ilike(f"%{token_hash[:8]}%"),
            SecurityAlert.status == "OPEN",
        )
    ).scalar_one_or_none()

    if existing:
        existing.occurrence_count += 1
        existing.last_updated_at = datetime.now(timezone.utc)
    else:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            category="DENIED_ACCESS",
            severity="MEDIUM",
            title=f"Invalid Visitor QR Scanned — Token [{token_hash[:8]}]",
            description=f"An unrecognized QR code was presented at the gate (hash prefix: {token_hash[:16]}).",
            status="OPEN",
        )
        db.add(alert)
    db.commit()


# ---------------------------------------------------------------------------
# Query & Metrics Helpers
# ---------------------------------------------------------------------------
def get_visitor_metrics(db: Session) -> dict:
    """Return live counts for visitor dashboard."""
    now = datetime.now(timezone.utc)

    active_passes = db.execute(
        select(func.count()).select_from(VisitorPass).where(
            VisitorPass.status == "ISSUED",
            VisitorPass.valid_until >= now,
        )
    ).scalar() or 0

    pending_approvals = db.execute(
        select(func.count()).select_from(VisitorApproval).where(
            VisitorApproval.status == "PENDING"
        )
    ).scalar() or 0

    visitors_inside = db.execute(
        select(func.count()).select_from(VisitorPass).where(
            VisitorPass.status == "ACTIVE_INSIDE"
        )
    ).scalar() or 0

    # Completed today in UTC/IST
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today = db.execute(
        select(func.count()).select_from(VisitorPass).where(
            VisitorPass.status == "COMPLETED",
            VisitorPass.check_out_at >= today_start,
        )
    ).scalar() or 0

    revoked_or_expired = db.execute(
        select(func.count()).select_from(VisitorPass).where(
            or_(
                VisitorPass.status.in_(["REVOKED", "EXPIRED", "DENIED"]),
                (VisitorPass.status == "ISSUED") & (VisitorPass.valid_until < now),
            )
        )
    ).scalar() or 0

    return {
        "active_passes": int(active_passes),
        "pending_approvals": int(pending_approvals),
        "visitors_inside": int(visitors_inside),
        "completed_today": int(completed_today),
        "revoked_or_expired": int(revoked_or_expired),
    }
