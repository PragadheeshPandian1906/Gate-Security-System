"""
SmartGuard AI — Phase 4 Security Contacts API Routes
All endpoints require ADMIN role — enforced via require_admin dependency.

Endpoints:
  GET    /api/admin/security-contacts              — list contacts
  POST   /api/admin/security-contacts              — create contact
  GET    /api/admin/security-contacts/{contact_id} — get contact
  PUT    /api/admin/security-contacts/{contact_id} — update contact
  DELETE /api/admin/security-contacts/{contact_id} — delete contact
  POST   /api/admin/security-contacts/{contact_id}/test-email — send test email
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.alerts import SecurityContact
from app.schemas.alerts import (
    SecurityContactCreate,
    SecurityContactUpdate,
    SecurityContactResponse,
)
from app.services import notification_service

router = APIRouter(prefix="/admin/security-contacts", tags=["Security Contacts"])
logger = logging.getLogger("smartguard.contacts")


def _contact_to_response(c: SecurityContact) -> SecurityContactResponse:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return SecurityContactResponse(
        id=str(c.id),
        full_name=c.full_name,
        email=c.email,
        is_active=c.is_active,
        notify_categories=c.notify_categories,
        min_severity=c.min_severity,
        daily_summary_enabled=c.daily_summary_enabled,
        created_at=c.created_at or now,
        updated_at=c.updated_at or now,
        last_notified_at=c.last_notified_at,
        last_notification_status=c.last_notification_status,
    )


@router.get("/config-status")
def get_email_config_status(
    _admin: SecurityAccount = Depends(require_admin),
):
    """Return non-sensitive status of the backend email configuration."""
    from app.core.config import get_settings
    settings = get_settings()
    return {
        "email_enabled": settings.email_enabled,
        "email_provider": settings.email_provider,
        "from_address": settings.email_from_address,
        "from_name": settings.email_from_name,
        "has_api_key": bool(settings.email_api_key or settings.smtp_host),
    }


@router.get("", response_model=List[SecurityContactResponse])
def list_contacts(
    search: Optional[str] = Query(None, description="Search by name or email"),
    is_active: Optional[bool] = Query(None, description="Filter active/inactive"),
    db: Session = Depends(get_db),
    _admin: SecurityAccount = Depends(require_admin),
) -> List[SecurityContactResponse]:
    """List all configured external security contacts for email notifications."""
    query = select(SecurityContact)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                SecurityContact.full_name.ilike(term),
                SecurityContact.email.ilike(term),
            )
        )
    if is_active is not None:
        query = query.where(SecurityContact.is_active == is_active)

    query = query.order_by(SecurityContact.created_at.desc())
    contacts = db.execute(query).scalars().all()
    return [_contact_to_response(c) for c in contacts]


@router.post("", response_model=SecurityContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    body: SecurityContactCreate,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> SecurityContactResponse:
    """Create a new security contact for email alerts and daily summaries."""
    # Check email duplicate
    email_clean = body.email.strip().lower()
    existing = db.execute(
        select(SecurityContact).where(SecurityContact.email.ilike(email_clean))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Security contact with email '{body.email}' already exists.",
        )

    # Validate min_severity
    min_sev = body.min_severity.upper()
    if min_sev not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_severity must be one of LOW, MEDIUM, HIGH, CRITICAL",
        )

    contact = SecurityContact(
        id=uuid.uuid4(),
        full_name=body.full_name.strip(),
        email=email_clean,
        is_active=body.is_active,
        notify_categories=body.notify_categories,
        min_severity=min_sev,
        daily_summary_enabled=body.daily_summary_enabled,
        created_by=admin.id,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    logger.info("Created security contact: email=%s by admin=%s", contact.email, admin.username)
    return _contact_to_response(contact)


@router.get("/{contact_id}", response_model=SecurityContactResponse)
def get_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: SecurityAccount = Depends(require_admin),
) -> SecurityContactResponse:
    """Get security contact details."""
    contact = db.execute(
        select(SecurityContact).where(SecurityContact.id == contact_id)
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return _contact_to_response(contact)


@router.put("/{contact_id}", response_model=SecurityContactResponse)
def update_contact(
    contact_id: uuid.UUID,
    body: SecurityContactUpdate,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
) -> SecurityContactResponse:
    """Update a security contact's preferences or active state."""
    contact = db.execute(
        select(SecurityContact).where(SecurityContact.id == contact_id)
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if body.email is not None:
        email_clean = body.email.strip().lower()
        if email_clean != contact.email:
            existing = db.execute(
                select(SecurityContact).where(
                    SecurityContact.email.ilike(email_clean),
                    SecurityContact.id != contact_id,
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Security contact with email '{body.email}' already exists.",
                )
            contact.email = email_clean

    if body.full_name is not None:
        contact.full_name = body.full_name.strip()
    if body.is_active is not None:
        contact.is_active = body.is_active
    if body.notify_categories is not None:
        contact.notify_categories = body.notify_categories
    if body.min_severity is not None:
        min_sev = body.min_severity.upper()
        if min_sev not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_severity must be one of LOW, MEDIUM, HIGH, CRITICAL",
            )
        contact.min_severity = min_sev
    if body.daily_summary_enabled is not None:
        contact.daily_summary_enabled = body.daily_summary_enabled

    db.add(contact)
    db.commit()
    db.refresh(contact)

    logger.info("Updated security contact: id=%s by admin=%s", contact.id, admin.username)
    return _contact_to_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: SecurityAccount = Depends(require_admin),
):
    """Delete a security contact."""
    contact = db.execute(
        select(SecurityContact).where(SecurityContact.id == contact_id)
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    db.delete(contact)
    db.commit()
    logger.info("Deleted security contact: id=%s by admin=%s", contact_id, admin.username)
    return None


@router.post("/{contact_id}/test-email")
def test_contact_email(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: SecurityAccount = Depends(require_admin),
):
    """Send a test email to verify delivery to this contact."""
    result = notification_service.send_test_email(db, str(contact_id))
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Test email delivery failed."),
        )
    return {"message": "Test email sent successfully."}
