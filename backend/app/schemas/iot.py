"""
SmartGuard AI — IoT WebSocket Schemas
Validation models for ESP32 Gate Controller communication.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Device to Backend (Incoming) ─────────────────────────────────────────────

class DeviceAuthPayload(BaseModel):
    """Optional message payload if authenticating via first WebSocket frame."""
    type: Literal["AUTH"] = "AUTH"
    device_id: str = Field(..., min_length=1, max_length=64)
    token: str = Field(..., min_length=1, max_length=256)


class DeviceHeartbeatPayload(BaseModel):
    """Periodic keep-alive from ESP32."""
    type: Literal["HEARTBEAT"] = "HEARTBEAT"
    device_id: str = Field(..., min_length=1, max_length=64)
    state: Literal["CLOSED", "OPEN", "OPENING", "CLOSING", "UNKNOWN"] = "CLOSED"


class DeviceCommandAckPayload(BaseModel):
    """Command receipt acknowledgement from ESP32."""
    type: Literal["COMMAND_ACK"] = "COMMAND_ACK"
    command_id: str = Field(..., min_length=1, max_length=64)
    status: Literal["ACCEPTED", "REJECTED", "FAILED", "COMPLETED"]
    detail: Optional[str] = Field(default=None, max_length=256)


class DeviceGateStatePayload(BaseModel):
    """Controller-reported state transition."""
    type: Literal["GATE_STATE"] = "GATE_STATE"
    device_id: str = Field(..., min_length=1, max_length=64)
    state: Literal["CLOSED", "OPEN", "OPENING", "CLOSING", "UNKNOWN"]
    command_id: Optional[str] = Field(default=None, max_length=64)


# ── Backend to Device (Outgoing) ─────────────────────────────────────────────

class GateOpenCommand(BaseModel):
    """Command to actuate barrier open."""
    type: Literal["GATE_OPEN"] = "GATE_OPEN"
    command_id: str
    attempt_id: Optional[str] = None
    duration_ms: int = Field(default=15000, ge=1000, le=60000)
    message: str = Field(default="ACCESS GRANTED", max_length=16)


class GateCloseCommand(BaseModel):
    """Command to actuate barrier close."""
    type: Literal["GATE_CLOSE"] = "GATE_CLOSE"
    command_id: str
    reason: str = Field(default="OPERATOR_RESET", max_length=64)


class DisplayStatusCommand(BaseModel):
    """Command to update 16x2 LCD status."""
    type: Literal["DISPLAY_STATUS"] = "DISPLAY_STATUS"
    message_id: str
    line1: str = Field(..., max_length=16)
    line2: str = Field(..., max_length=16)


# ── Telemetry & Event Log Types ──────────────────────────────────────────────

class IoTSystemEvent(BaseModel):
    """Structured event for the monitoring dashboard and diagnostics."""
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: Literal["INFO", "SUCCESS", "WARNING", "ERROR"]
    source: Literal["ESP32", "BACKEND", "OPERATOR"]
    event_type: str
    message: str
    details: Optional[dict] = None
