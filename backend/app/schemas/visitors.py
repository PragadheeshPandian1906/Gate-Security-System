"""
SmartGuard AI — Phase 5 Visitor Management Pydantic Schemas
"""
import uuid
from datetime import datetime
from typing import Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class VisitorPassSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Union[uuid.UUID, str]
    pass_number: str
    status: str
    valid_from: datetime
    valid_until: datetime
    purpose: str


class VisitorRegistrationRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=256)
    organization: Optional[str] = Field(None, max_length=128)
    id_type: Optional[str] = Field(None, max_length=64)
    id_number: Optional[str] = Field(None, max_length=64)
    notes: Optional[str] = None


class VisitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Union[uuid.UUID, str]
    full_name: str
    person_type: str = "visitor"
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    total_visits: int = 0
    active_pass: Optional[VisitorPassSummary] = None


class VisitorPassCreateRequest(BaseModel):
    visitor_id: Optional[Union[uuid.UUID, str]] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    host_person_id: Optional[Union[uuid.UUID, str]] = None
    vehicle_id: Optional[Union[uuid.UUID, str]] = None
    vehicle_plate: Optional[str] = None
    purpose: str = Field("Campus Meeting", max_length=128)
    organization: Optional[str] = Field(None, max_length=128)
    id_type: Optional[str] = Field(None, max_length=64)
    id_number: Optional[str] = Field(None, max_length=64)
    valid_from: datetime
    valid_until: datetime
    send_email: bool = True


class VisitorPassResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Union[uuid.UUID, str]
    pass_number: str
    visitor_id: Union[uuid.UUID, str]
    visitor_name: str
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    host_person_id: Optional[Union[uuid.UUID, str]] = None
    host_name: Optional[str] = None
    vehicle_id: Optional[Union[uuid.UUID, str]] = None
    vehicle_plate: Optional[str] = None
    purpose: str
    organization: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    valid_from: datetime
    valid_until: datetime
    status: str
    qr_code_path: Optional[str] = None
    qr_code_base64: Optional[str] = None
    qr_image_base64: Optional[str] = None
    issued_at: datetime
    issued_by_name: Optional[str] = None
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None
    email_delivery_status: Optional[str] = None


class VisitorPassRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=512)


class VisitorScanRequest(BaseModel):
    qr_credential: str = Field(..., min_length=5, description="Scanned QR code raw token or SGVP:token")
    direction: Literal["ENTRY", "EXIT"] = "ENTRY"


class VisitorScanResult(BaseModel):
    status: Literal["PENDING_APPROVAL", "APPROVED", "DENIED", "ERROR", "COMPLETED"]
    message: str
    pass_id: Optional[Union[uuid.UUID, str]] = None
    pass_number: Optional[str] = None
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    host_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    purpose: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    direction: str
    approval_id: Optional[Union[uuid.UUID, str]] = None
    gate_state: Optional[str] = None
    schedule_status: Optional[str] = None


class VisitorApprovalDecisionRequest(BaseModel):
    decision: Optional[str] = Field(None, description="APPROVE or DENY")
    denial_reason: Optional[str] = Field(None, max_length=512)
    notes: Optional[str] = None


class VisitorApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Union[uuid.UUID, str]
    pass_id: Union[uuid.UUID, str]
    pass_number: str
    visitor_id: Union[uuid.UUID, str]
    visitor_name: str
    host_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    purpose: str
    direction: str
    status: str
    scanned_at: datetime
    scanned_by_name: Optional[str] = None
    decision_by_name: Optional[str] = None
    decision_at: Optional[datetime] = None
    denial_reason: Optional[str] = None
    notes: Optional[str] = None
    valid_from: datetime
    valid_until: datetime


class ActiveVisitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pass_id: Union[uuid.UUID, str]
    pass_number: str
    visitor_id: Union[uuid.UUID, str]
    visitor_name: str
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    host_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    purpose: str
    organization: Optional[str] = None
    check_in_at: datetime
    valid_until: datetime
    duration_minutes: int


class VisitorMetricsResponse(BaseModel):
    active_passes: int
    pending_approvals: int
    visitors_inside: int
    completed_today: int
    revoked_or_expired: int
