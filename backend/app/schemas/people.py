"""
SmartGuard AI — Phase 2 Pydantic Schemas

Covers: campus_people, vehicles, face_profiles, verifications.
"""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Campus People
# ---------------------------------------------------------------------------

class CampusPersonCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=128)
    person_type: str = Field(default="staff", pattern="^(staff|student|visitor|contractor)$")
    employee_id: Optional[str] = Field(default=None, max_length=64)
    department: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=256)
    phone: Optional[str] = Field(default=None, max_length=32)
    status: str = Field(default="active", pattern="^(active|inactive|suspended)$")
    notes: Optional[str] = None


class CampusPersonUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    person_type: Optional[str] = Field(default=None, pattern="^(staff|student|visitor|contractor)$")
    employee_id: Optional[str] = Field(default=None, max_length=64)
    department: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=256)
    phone: Optional[str] = Field(default=None, max_length=32)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive|suspended)$")
    notes: Optional[str] = None


class CampusPersonOut(BaseModel):
    id: uuid.UUID
    full_name: str
    person_type: str
    employee_id: Optional[str]
    department: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    status: str
    notes: Optional[str]
    photo_path: Optional[str]
    photo_storage_path: Optional[str]
    created_at: datetime
    updated_at: datetime
    registered_by: Optional[uuid.UUID]
    face_profile_count: int = 0

    model_config = {"from_attributes": True}


class CampusPersonListOut(BaseModel):
    total: int
    items: List[CampusPersonOut]


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

class VehicleCreate(BaseModel):
    plate_number: str = Field(..., min_length=1, max_length=32)
    make: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=64)
    color: Optional[str] = Field(default=None, max_length=32)
    vehicle_type: Optional[str] = Field(default=None, max_length=32)
    owner_name: Optional[str] = Field(default=None, max_length=128)
    owner_person_id: Optional[uuid.UUID] = None
    status: str = Field(default="active", pattern="^(active|inactive|flagged)$")
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    plate_number: Optional[str] = Field(default=None, min_length=1, max_length=32)
    make: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=64)
    color: Optional[str] = Field(default=None, max_length=32)
    vehicle_type: Optional[str] = Field(default=None, max_length=32)
    owner_name: Optional[str] = Field(default=None, max_length=128)
    owner_person_id: Optional[uuid.UUID] = None
    status: Optional[str] = Field(default=None, pattern="^(active|inactive|flagged)$")
    notes: Optional[str] = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    plate_number: str
    plate_normalized: str
    make: Optional[str]
    model: Optional[str]
    color: Optional[str]
    vehicle_type: Optional[str]
    owner_name: Optional[str]
    owner_person_id: Optional[uuid.UUID]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    registered_by: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class VehicleListOut(BaseModel):
    total: int
    items: List[VehicleOut]


# ---------------------------------------------------------------------------
# Face Profiles
# ---------------------------------------------------------------------------

class FaceProfileOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID
    embedding_model: str
    image_path: Optional[str]
    image_storage_path: Optional[str]
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Verification Results
# ---------------------------------------------------------------------------

class FaceVerifyResponse(BaseModel):
    """Response from a face verification attempt."""
    result: str  # matched | no_match | low_confidence | error | no_face
    confidence: Optional[float]
    distance: Optional[float]
    matched_person: Optional[dict]  # {id, name, type}
    faces_detected: int
    candidates: List[dict]
    verification_id: Optional[str]
    storage: Optional[dict]
    error: Optional[str]


class AlprVerifyResponse(BaseModel):
    """Response from an ALPR verification attempt."""
    result: str  # matched | no_match | no_plate | error
    detected_plate: Optional[str]
    detected_plate_normalized: Optional[str]
    detection_confidence: Optional[float]
    ocr_confidence: Optional[float]
    vehicle_match: Optional[dict]
    all_plates: List[dict]
    verification_id: Optional[str]
    storage: Optional[dict]
    error: Optional[str]


# ---------------------------------------------------------------------------
# Verification History
# ---------------------------------------------------------------------------

class FaceVerificationOut(BaseModel):
    id: uuid.UUID
    result: str
    confidence: Optional[float]
    distance: Optional[float]
    matched_person_id: Optional[uuid.UUID]
    faces_detected: int
    verified_by: Optional[uuid.UUID]
    timestamp: datetime

    model_config = {"from_attributes": True}


class AlprVerificationOut(BaseModel):
    id: uuid.UUID
    result: str
    detected_plate: Optional[str]
    detected_plate_normalized: Optional[str]
    detection_confidence: Optional[float]
    ocr_confidence: Optional[float]
    matched_vehicle_id: Optional[uuid.UUID]
    verified_by: Optional[uuid.UUID]
    timestamp: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Live Frame Detection Schemas
# ---------------------------------------------------------------------------

class LivePersonSummary(BaseModel):
    id: str
    name: str
    person_type: Optional[str] = None
    department: Optional[str] = None


class LiveVehicleSummary(BaseModel):
    id: str
    plate_number: str
    status: str
    owner_name: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None


class LiveFaceDetection(BaseModel):
    box: List[int]                         # [x1, y1, x2, y2]
    score_type: str = "cosine_similarity"  # clearly identified
    score: Optional[float] = None          # cosine similarity
    distance: Optional[float] = None       # cosine distance
    matched: bool = False
    status: str                            # matched | unknown | low_confidence | no_enrolled | detected_only
    label: str
    person: Optional[LivePersonSummary] = None


class LivePlateDetection(BaseModel):
    box: List[int]                         # [x1, y1, x2, y2]
    plate_text: Optional[str] = None
    normalized_plate: Optional[str] = None
    detection_confidence: Optional[float] = None
    ocr_confidence: Optional[float] = None
    registered: bool = False
    status: str                            # registered | unregistered | flagged | unreadable | unavailable
    label: str
    vehicle: Optional[LiveVehicleSummary] = None


class LiveFrameTiming(BaseModel):
    total_latency_ms: float
    face_latency_ms: float
    plate_latency_ms: float


class LiveFrameErrors(BaseModel):
    face_error: Optional[str] = None
    plate_error: Optional[str] = None


class LiveFrameResponse(BaseModel):
    frame_id: str
    timestamp: float
    image_width: int
    image_height: int
    faces: List[LiveFaceDetection] = []
    plates: List[LivePlateDetection] = []
    timing: LiveFrameTiming
    errors: LiveFrameErrors
    storage: Optional[dict] = None
    face_verification_id: Optional[str] = None
    alpr_verification_id: Optional[str] = None

