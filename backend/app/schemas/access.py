"""
SmartGuard AI — Phase 3 Pydantic Schemas

Covers: access attempts, gate status, access schedules, watchlist entries.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Access Attempt schemas
# ---------------------------------------------------------------------------

class AccessAttemptCreate(BaseModel):
    """Request body to submit a new access attempt."""
    direction: str = Field(..., pattern="^(ENTRY|EXIT)$")
    face_verification_id: Optional[str] = None
    alpr_verification_id: Optional[str] = None


class FaceContext(BaseModel):
    result: Optional[str] = None
    confidence: Optional[float] = None
    matched_person: Optional[dict] = None


class PlateContext(BaseModel):
    detected_plate: Optional[str] = None
    detected_plate_normalized: Optional[str] = None
    matched_vehicle: Optional[dict] = None


class ScheduleContext(BaseModel):
    ok: Optional[bool] = None
    reason_code: Optional[str] = None
    detail: Optional[str] = None
    evaluated_local: Optional[str] = None
    weekday: Optional[str] = None
    schedule_open_time: Optional[str] = None
    schedule_close_time: Optional[str] = None
    campus_timezone: Optional[str] = None


class WatchlistContext(BaseModel):
    hit: Optional[bool] = None
    severity: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    entry_id: Optional[str] = None
    entry_reason: Optional[str] = None


class AccessAttemptResponse(BaseModel):
    """Full response from the access decision engine."""
    attempt_id: str
    direction: str
    decision: str  # ALLOW | DENY | MANUAL_REVIEW
    gate_result: str  # OPEN | CLOSED | MANUAL_REVIEW
    reason_codes: list[str]
    reason_text: str
    face: FaceContext
    plate: PlateContext
    ownership_ok: Optional[bool] = None
    schedule: Optional[ScheduleContext] = None
    watchlist: Optional[WatchlistContext] = None
    processing_ms: float


class AccessAttemptSummary(BaseModel):
    """Compact list item for access history."""
    id: str
    timestamp: datetime
    direction: str
    decision: str
    gate_result: str
    reason_codes: Optional[list] = None
    reason_text: Optional[str] = None
    detected_plate: Optional[str] = None
    matched_person_id: Optional[str] = None
    matched_vehicle_id: Optional[str] = None
    person_status: Optional[str] = None
    vehicle_status: Optional[str] = None
    ownership_ok: Optional[bool] = None
    schedule_ok: Optional[bool] = None
    watchlist_hit: Optional[bool] = None
    watchlist_severity: Optional[str] = None
    review_required: bool = False
    review_resolved: bool = False
    review_resolution: Optional[str] = None
    review_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    initiated_by: Optional[str] = None
    processing_ms: Optional[float] = None

    model_config = {"from_attributes": True}


class CampusHourlyAuthorization(BaseModel):
    hour: int
    entry_authorizations: int
    exit_authorizations: int


class CampusAccessActivity(BaseModel):
    id: str
    timestamp: datetime
    person_name: Optional[str] = None
    person_category: Optional[str] = None
    direction: str
    decision: str
    movement_status: str = "NOT_VERIFIED"


class CampusAnalyticsResponse(BaseModel):
    campus_timezone: str
    movement_tracking_available: bool = False
    movement_limitation: str
    total_entries_today: Optional[int] = None
    currently_inside: Optional[int] = None
    total_exits_today: Optional[int] = None
    denied_access_today: int
    occupancy_by_category: Optional[dict[str, int]] = None
    supported_person_categories: list[str]
    hourly_activity: list[CampusHourlyAuthorization]
    recent_activity: list[CampusAccessActivity]


class ManualReviewResolve(BaseModel):
    """Request body to resolve a pending manual review."""
    resolution: str = Field(..., pattern="^(approved|denied)$")
    reason: str = Field(..., min_length=3, max_length=512)


# ---------------------------------------------------------------------------
# Gate schemas
# ---------------------------------------------------------------------------

class GateStatusResponse(BaseModel):
    state: str  # OPEN | CLOSED | MANUAL_REVIEW | MANUAL_LATCHED_OPEN
    last_decision: Optional[str] = None
    last_direction: Optional[str] = None
    last_attempt_id: Optional[str] = None
    last_transition_at: Optional[str] = None
    simulation_note: str
    iot_controller: Optional[dict] = None


# ---------------------------------------------------------------------------
# Access Schedule schemas
# ---------------------------------------------------------------------------

class ScheduleEntry(BaseModel):
    id: Optional[str] = None
    weekday: str
    is_open: bool
    open_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    close_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    campus_timezone: str = "Asia/Kolkata"

    model_config = {"from_attributes": True}


class ScheduleUpdateRequest(BaseModel):
    """PUT /access/schedule — replace full weekly schedule."""
    entries: list[ScheduleEntry]
    campus_timezone: str = "Asia/Kolkata"


class ScheduleResponse(BaseModel):
    entries: list[ScheduleEntry]
    campus_timezone: str
    current_local_time: str
    today_weekday: str
    today_is_open: bool
    today_open_time: Optional[str] = None
    today_close_time: Optional[str] = None


# ---------------------------------------------------------------------------
# Watchlist schemas
# ---------------------------------------------------------------------------

class WatchlistEntryCreate(BaseModel):
    vehicle_id: Optional[str] = None
    plate_raw: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=512)
    severity: str = Field(default="medium", pattern="^(low|medium|high)$")
    expires_at: Optional[datetime] = None


class WatchlistEntryUpdate(BaseModel):
    reason: Optional[str] = Field(None, min_length=3, max_length=512)
    severity: Optional[str] = Field(None, pattern="^(low|medium|high)$")
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class WatchlistEntryResponse(BaseModel):
    id: str
    vehicle_id: Optional[str] = None
    plate_raw: Optional[str] = None
    plate_normalized: Optional[str] = None
    reason: str
    severity: str
    is_active: bool
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None
    resolved_by: Optional[str] = None

    model_config = {"from_attributes": True}
