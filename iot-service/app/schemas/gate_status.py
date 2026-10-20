"""
SmartGuard AI — IoT Microservice Schemas
Pydantic models for all API contracts and WebSocket protocol messages.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Automated gate statuses published by the main backend
# ─────────────────────────────────────────────────────────────────────────────

AutomatedGateStatus = Literal["GATE_OPEN", "MANUAL_REVIEW", "GATE_CLOSED"]
ManualGateCommand = Literal["MANUAL_GATE_OPEN", "MANUAL_GATE_CLOSE"]


class GateStatusRequest(BaseModel):
    """
    Authenticated request from the main backend to publish an automated gate decision.
    Only automated statuses are accepted here. Manual operator commands use separate endpoints.
    """
    status: AutomatedGateStatus
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    # Optional metadata for logging/tracing
    attempt_id: Optional[str] = Field(default=None, max_length=64)
    reason: Optional[str] = Field(default=None, max_length=256)
    command_issued_at_ns: Optional[int] = Field(default=None, ge=1)
    duration_ms: Optional[int] = Field(default=None, ge=1000, le=60000)


class ManualOpenRequest(BaseModel):
    """Operator manual open request. Requires SECURITY or ADMIN role."""
    reason: Optional[str] = Field(default="Manual operator action", max_length=256)
    command_issued_at_ns: Optional[int] = Field(default=None, ge=1)


class ManualCloseRequest(BaseModel):
    """Operator manual close request. Requires SECURITY or ADMIN role."""
    reason: Optional[str] = Field(default="Manual operator close", max_length=256)
    command_type: Literal["AUTOMATED", "MANUAL"] = "MANUAL"
    command_issued_at_ns: Optional[int] = Field(default=None, ge=1)


class DisplayStatusRequest(BaseModel):
    line1: str = Field(..., max_length=16)
    line2: str = Field(..., max_length=16)


# ─────────────────────────────────────────────────────────────────────────────
# Command results
# ─────────────────────────────────────────────────────────────────────────────

class CommandResult(BaseModel):
    """Result of a dispatched command to the ESP32."""
    success: bool
    delivered: bool = False
    controller_acknowledged: bool = False
    physical_position_confirmed: bool = False
    command_id: Optional[str] = None
    status: str  # SENT | EXECUTED | REJECTED | FAILED | DEVICE_OFFLINE | ACK_TIMEOUT | DUPLICATE
    detail: Optional[str] = None
    error: Optional[str] = None


class GateStatusResponse(BaseModel):
    """Response returned from POST /api/v1/gate/status."""
    accepted: bool
    event_id: str
    requested_status: str
    command_result: CommandResult
    message: str


class ManualCommandResponse(BaseModel):
    """Response returned from manual open/close endpoints."""
    accepted: bool
    command_type: str
    command_result: CommandResult
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# ESP32 Device → Microservice (Incoming WebSocket packets)
# ─────────────────────────────────────────────────────────────────────────────

class DeviceAuthPayload(BaseModel):
    type: Literal["AUTH"] = "AUTH"
    device_id: str = Field(..., min_length=1, max_length=64)
    token: str = Field(..., min_length=1, max_length=256)


class DeviceHeartbeatPayload(BaseModel):
    model_config = {"populate_by_name": True}
    type: Literal["HEARTBEAT"] = "HEARTBEAT"
    device_id: str = Field(..., min_length=1, max_length=64)
    gate_mode: Literal["AUTOMATED", "MANUAL_LATCHED_OPEN"] = "AUTOMATED"
    state: Literal["CLOSED", "OPEN", "OPENING", "CLOSING", "UNKNOWN"] = Field(
        default="CLOSED",
        validation_alias=AliasChoices("state", "gate_state"),
    )
    uptime_seconds: Optional[int] = None
    wifi_rssi: Optional[int] = None
    free_heap: Optional[int] = None


class DeviceCommandAckPayload(BaseModel):
    type: Literal["COMMAND_ACK", "GATE_ACTION_ACK"] = "COMMAND_ACK"
    command_id: str = Field(..., min_length=1, max_length=64)
    status: Literal["ACCEPTED", "REJECTED", "FAILED", "COMPLETED", "EXECUTED"]
    detail: Optional[str] = Field(default=None, max_length=256)


class DeviceGateStatePayload(BaseModel):
    type: Literal["GATE_STATE"] = "GATE_STATE"
    device_id: str = Field(..., min_length=1, max_length=64)
    state: Literal["CLOSED", "OPEN", "OPENING", "CLOSING", "UNKNOWN"] = Field(
        default="CLOSED",
        validation_alias=AliasChoices("state", "gate_state"),
    )
    gate_mode: Literal["AUTOMATED", "MANUAL_LATCHED_OPEN"] = "AUTOMATED"
    command_id: Optional[str] = Field(default=None, max_length=64)


# ─────────────────────────────────────────────────────────────────────────────
# Microservice → ESP32 (Outgoing WebSocket commands)
# ─────────────────────────────────────────────────────────────────────────────

class GateOpenCommand(BaseModel):
    type: Literal["GATE_OPEN"] = "GATE_OPEN"
    command_id: str
    command_sequence: int = Field(ge=1)
    command_type: Literal["AUTOMATED", "MANUAL"] = "AUTOMATED"
    attempt_id: Optional[str] = None
    duration_ms: int = Field(default=15000, ge=1000, le=60000)
    line1: str = Field(default="GATE OPEN", max_length=16)
    line2: str = Field(default="WELCOME", max_length=16)


class GateCloseCommand(BaseModel):
    type: Literal["GATE_CLOSE"] = "GATE_CLOSE"
    command_id: str
    command_sequence: int = Field(ge=1)
    command_type: Literal["AUTOMATED", "MANUAL"] = "AUTOMATED"
    reason: str = Field(default="OPERATOR_RESET", max_length=64)
    line1: str = Field(default="GATE CLOSED", max_length=16)
    line2: str = Field(default="PLEASE WAIT", max_length=16)


class DisplayStatusCommand(BaseModel):
    type: Literal["DISPLAY_STATUS"] = "DISPLAY_STATUS"
    message_id: str
    line1: str = Field(..., max_length=16)
    line2: str = Field(..., max_length=16)


# ─────────────────────────────────────────────────────────────────────────────
# Device health and monitoring
# ─────────────────────────────────────────────────────────────────────────────

class DeviceStatusSnapshot(BaseModel):
    """Full device health snapshot returned by GET /api/v1/device/status."""
    is_connected: bool
    is_healthy: bool
    device_id: Optional[str]
    client_ip: Optional[str]
    connected_at: Optional[str]
    last_heartbeat_at: Optional[str]
    heartbeat_age_seconds: Optional[float]
    reported_gate_state: str
    reported_gate_mode: str
    last_requested_status: Optional[str]
    last_command_id: Optional[str]
    last_command_type: Optional[str]
    last_ack_status: Optional[str]
    configured_device_id: str
    auto_close_duration_ms: int
    uptime_seconds: Optional[int] = None
    wifi_rssi: Optional[int] = None
    free_heap: Optional[int] = None


class IoTSystemEvent(BaseModel):
    """Structured event for the monitoring dashboard and diagnostics."""
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: Literal["INFO", "SUCCESS", "WARNING", "ERROR"]
    source: Literal["ESP32", "BACKEND", "OPERATOR", "SYSTEM"]
    event_type: str
    message: str
    details: Optional[dict] = None
