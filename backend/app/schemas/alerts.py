"""
SmartGuard AI — Phase 4 Pydantic Schemas

Schemas for:
  - SecurityAlert (list, detail, lifecycle actions)
  - AlertNote
  - SecurityContact (CRUD)
  - NotificationLog (list, retry)
  - Reports (access list, CSV, daily summary)
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List, Any, Union
from pydantic import BaseModel, EmailStr, Field


# ============================================================
# Alert Schemas
# ============================================================

class AlertSummary(BaseModel):
    id: Union[uuid.UUID, str]
    category: str
    severity: str
    title: str
    status: str
    detected_plate: Optional[str] = None
    person_id: Optional[Union[uuid.UUID, str]] = None
    vehicle_id: Optional[Union[uuid.UUID, str]] = None
    access_attempt_id: Optional[Union[uuid.UUID, str]] = None
    first_detected_at: datetime
    last_updated_at: datetime
    occurrence_count: int

    model_config = {"from_attributes": True}


class AlertNoteSchema(BaseModel):
    id: Union[uuid.UUID, str]
    alert_id: Union[uuid.UUID, str]
    author_id: Optional[Union[uuid.UUID, str]] = None
    note_type: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertDetail(AlertSummary):
    description: Optional[str] = None
    watchlist_entry_id: Optional[Union[uuid.UUID, str]] = None
    related_attempt_ids: Optional[List[str]] = None
    assigned_to: Optional[Union[uuid.UUID, str]] = None
    acknowledged_by: Optional[Union[uuid.UUID, str]] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[Union[uuid.UUID, str]] = None
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None
    notes: List[AlertNoteSchema] = Field(default_factory=list)


class AlertMetrics(BaseModel):
    open: int
    acknowledged: int
    investigating: int
    resolved: int
    dismissed: int
    critical_high_unresolved: int
    total_unresolved: int


class AlertListResponse(BaseModel):
    items: List[AlertSummary]
    total: int
    skip: int
    limit: int


class AlertLifecycleAction(BaseModel):
    """Used for acknowledge, start_investigation, resolve, dismiss."""
    reason: Optional[str] = Field(default=None, max_length=512)


class AddAlertNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


# ============================================================
# Security Contact Schemas
# ============================================================

class SecurityContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    is_active: bool = True
    notify_categories: Optional[List[str]] = None
    min_severity: str = Field(default="HIGH")
    daily_summary_enabled: bool = True


class SecurityContactUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    notify_categories: Optional[List[str]] = None
    min_severity: Optional[str] = None
    daily_summary_enabled: Optional[bool] = None


class SecurityContactResponse(BaseModel):
    id: Union[uuid.UUID, str]
    full_name: str
    email: str
    is_active: bool
    notify_categories: Optional[List[str]] = None
    min_severity: str
    daily_summary_enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_notified_at: Optional[datetime] = None
    last_notification_status: Optional[str] = None

    model_config = {"from_attributes": True}


# ============================================================
# Notification Log Schemas
# ============================================================

class NotificationLogResponse(BaseModel):
    id: Union[uuid.UUID, str]
    notification_type: str
    alert_id: Optional[Union[uuid.UUID, str]] = None
    contact_id: Optional[Union[uuid.UUID, str]] = None
    recipient_email: str
    subject: str
    status: str
    attempt_count: int
    max_attempts: int
    created_at: datetime
    last_attempted_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    provider: Optional[str] = None
    # provider_message_id intentionally included (it's not a secret)
    provider_message_id: Optional[str] = None
    # error_detail: sanitized, no credentials
    error_detail: Optional[str] = None
    summary_date: Optional[str] = None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: List[NotificationLogResponse]
    total: int
    skip: int
    limit: int


# ============================================================
# Access Report Schemas
# ============================================================

class AccessReportRow(BaseModel):
    """Flat row for the access report table."""
    id: str
    timestamp: datetime
    direction: str
    decision: str
    gate_result: str
    reason_codes: Optional[List[str]] = None
    reason_text: Optional[str] = None
    detected_plate: Optional[str] = None
    detected_plate_normalized: Optional[str] = None
    matched_person_id: Optional[str] = None
    person_status: Optional[str] = None
    matched_vehicle_id: Optional[str] = None
    vehicle_status: Optional[str] = None
    ownership_ok: Optional[bool] = None
    schedule_ok: Optional[bool] = None
    watchlist_hit: Optional[bool] = None
    watchlist_severity: Optional[str] = None
    review_required: bool
    review_resolved: bool
    review_resolution: Optional[str] = None
    review_reason: Optional[str] = None
    initiated_by: Optional[str] = None
    processing_ms: Optional[float] = None
    visitor_pass_id: Optional[str] = None
    visitor_pass_number: Optional[str] = None


class AccessReportResponse(BaseModel):
    items: List[AccessReportRow]
    total: int
    skip: int
    limit: int


# ============================================================
# Daily Summary Schema
# ============================================================

class DailySummaryResponse(BaseModel):
    date: str
    timezone: str
    # Access activity
    total: int
    allowed: int
    denied: int
    manual_review: int
    entry: int
    exit: int
    # Visitor activity
    visitor_entries: int = 0
    visitor_exits: int = 0
    active_visitors_inside: int = 0
    # Security activity
    new_alerts: int
    unresolved_alerts: int
    watchlist_incidents: int
    repeated_denials: int
    pending_reviews: int
    resolved_reviews: int
    # Top denial reasons
    top_denial_reasons: List[dict]


class SendDailySummaryRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    force: bool = False
