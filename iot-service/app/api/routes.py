"""
SmartGuard AI — IoT Microservice API Routes
Provides:
  - POST /api/v1/gate/status      — authenticated gate decisions from main backend
  - POST /api/v1/gate/manual-open — authorized manual open (SECURITY/ADMIN JWT)
  - POST /api/v1/gate/manual-close — authorized manual close (SECURITY/ADMIN JWT)
  - GET  /api/v1/device/status    — device health snapshot
  - GET  /api/v1/device/events    — recent event buffer
  - GET  /api/v1/health           — microservice health check
  - WebSocket /ws/monitor         — dashboard real-time telemetry
  - WebSocket /ws/iot/gate        — ESP32 device connection
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.schemas.gate_status import (
    GateStatusRequest,
    GateStatusResponse,
    ManualCloseRequest,
    ManualCommandResponse,
    ManualOpenRequest,
    CommandResult,
    DisplayStatusRequest,
)
from app.services.device_manager import device_manager

logger = logging.getLogger("iot.api")
router = APIRouter()
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Service-to-Service Authentication
# ─────────────────────────────────────────────────────────────────────────────

def verify_service_secret(x_service_secret: Annotated[str | None, Header()] = None) -> None:
    """
    Verify the internal service-to-service secret.
    Used on the automated gate status endpoint so that only the main backend can call it.
    Never exposed to the browser.
    """
    if not x_service_secret or x_service_secret != settings.iot_service_secret:
        logger.warning("iot.api Rejected request with invalid service secret")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service secret",
        )


def require_operator_secret(
    x_service_secret: Annotated[str | None, Header()] = None,
    x_operator_role: Annotated[str | None, Header()] = None,
    x_operator_id: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Manual operator commands require:
      1. Valid service secret (proves the request came through a trusted channel)
      2. Operator role and ID forwarded after the main backend validates its JWT.
    """
    if not x_service_secret or x_service_secret != settings.iot_service_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service secret",
        )
    if x_operator_role not in {"SECURITY", "ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SECURITY or ADMIN role required for gate control",
        )
    if not x_operator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated operator identity required",
        )
    return {"role": x_operator_role, "operator_id": x_operator_id}


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    status_data = device_manager.get_status()
    return {
        "status": "ok",
        "service": "SmartGuard IoT Microservice",
        "device_connected": status_data["is_connected"],
        "device_healthy": status_data["is_healthy"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Device Status & Events
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/device/status")
async def get_device_status(
    _secret: Annotated[None, Depends(verify_service_secret)],
):
    return device_manager.get_status()


@router.get("/device/events")
async def get_device_events(
    _secret: Annotated[None, Depends(verify_service_secret)],
):
    return device_manager.get_recent_events()


# ─────────────────────────────────────────────────────────────────────────────
# Automated Gate Status (main backend → IoT microservice)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/gate/status", response_model=GateStatusResponse)
async def publish_gate_status(
    body: GateStatusRequest,
    _secret: Annotated[None, Depends(verify_service_secret)],
):
    """
    Receive an automated gate decision from the main SmartGuard AI backend.
    Only GATE_OPEN, MANUAL_REVIEW, and GATE_CLOSED are accepted here.

    Idempotency: duplicate event_ids are silently accepted and return the same
    response structure without re-dispatching to the ESP32.
    """
    event_id = body.event_id

    # Idempotency check
    if device_manager.is_duplicate_event(event_id):
        logger.info("iot.api Duplicate event_id=%s ignored", event_id)
        return GateStatusResponse(
            accepted=True,
            event_id=event_id,
            requested_status=body.status,
            command_result=CommandResult(
                success=True,
                delivered=False,
                controller_acknowledged=False,
                physical_position_confirmed=False,
                status="DUPLICATE",
                detail="Event already processed",
            ),
            message="Duplicate event — already processed",
        )

    device_manager._requested_status = body.status

    device_manager.record_event(
        "INFO", "BACKEND", "STATUS_RECEIVED",
        f"Automated status from main backend: {body.status} (event={event_id[:8]})",
        {"status": body.status, "event_id": event_id, "attempt_id": body.attempt_id},
    )

    cmd_result: dict

    if body.status == "GATE_OPEN":
        cmd_result = await device_manager.send_gate_open(
            command_type="AUTOMATED",
            attempt_id=body.attempt_id,
            duration_ms=body.duration_ms,
            line1="GATE OPEN",
            line2="WELCOME",
            command_issued_at_ns=body.command_issued_at_ns,
        )
        msg = (
            "Controller acknowledged open-command execution; gate position is not sensor-verified."
            if cmd_result.get("success")
            else f"Controller rejected the open command: {cmd_result.get('detail', 'command not executed')}."
            if cmd_result.get("status") == "REJECTED"
            else "Open command was delivered, but no final controller acknowledgement was received."
            if cmd_result.get("delivered")
            else f"Gate open command failed: {cmd_result.get('error', 'unknown')}"
        )

    elif body.status == "MANUAL_REVIEW":
        await device_manager.send_display_status("MANUAL REVIEW", "WAIT FOR GUARD")
        cmd_result = {
            "success": False,
            "delivered": False,
            "controller_acknowledged": False,
            "physical_position_confirmed": False,
            "status": "DISPLAY_ONLY",
            "command_id": None,
        }
        msg = "MANUAL_REVIEW: LCD updated. Gate remains closed."

    else:  # GATE_CLOSED / DENY
        cmd_result = await device_manager.send_gate_close(
            command_type="AUTOMATED",
            reason="GATE_CLOSED",
            line1="GATE CLOSED",
            line2="PLEASE WAIT",
            command_issued_at_ns=body.command_issued_at_ns,
        )
        msg = (
            "Controller acknowledged close-command execution; gate position is not sensor-verified."
            if cmd_result.get("success")
            else f"Controller rejected the close command: {cmd_result.get('detail', 'command not executed')}."
            if cmd_result.get("status") == "REJECTED"
            else "Close command was delivered, but no final controller acknowledgement was received."
            if cmd_result.get("delivered")
            else f"Gate close command failed: {cmd_result.get('error', 'unknown')}"
        )

    return GateStatusResponse(
        accepted=True,
        event_id=event_id,
        requested_status=body.status,
        command_result=CommandResult(
            success=cmd_result.get("success", False),
            delivered=cmd_result.get("delivered", False),
            controller_acknowledged=cmd_result.get("controller_acknowledged", False),
            physical_position_confirmed=False,
            command_id=cmd_result.get("command_id"),
            status=cmd_result.get("status", "UNKNOWN"),
            detail=cmd_result.get("detail"),
            error=cmd_result.get("error"),
        ),
        message=msg,
    )


@router.post("/gate/display-status")
async def publish_display_status(
    body: DisplayStatusRequest,
    _secret: Annotated[None, Depends(verify_service_secret)],
):
    """Forward an authenticated LCD-only update; it never changes access decisions."""
    result = await device_manager.send_display_status(body.line1, body.line2)
    return {
        "accepted": True,
        "delivered": result.get("delivered", False),
        "controller_acknowledged": False,
        "physical_position_confirmed": False,
        "status": result.get("status", "UNKNOWN"),
        "error": result.get("error"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manual Gate Controls (operator → IoT microservice via secure proxy)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/gate/manual-open", response_model=ManualCommandResponse)
async def manual_gate_open(
    body: ManualOpenRequest,
    operator: Annotated[dict, Depends(require_operator_secret)],
):
    """
    Authorized operator manually opens the gate.
    Latches the gate open until an explicit manual-close command.
    Automated open timers do not apply to this command.
    """
    operator_id = operator.get("operator_id", "unknown")

    device_manager.record_event(
        "INFO", "OPERATOR", "MANUAL_OPEN_REQUESTED",
        f"Manual gate open requested by operator={operator_id}: {body.reason}",
        {"operator_id": operator_id, "reason": body.reason},
    )

    cmd_result = await device_manager.send_gate_open(
        command_type="MANUAL",
        line1="MANUAL GATE OPEN",
        line2="WAITING TO CLOSE",
        command_issued_at_ns=body.command_issued_at_ns,
    )

    if cmd_result.get("success"):
        msg = f"Controller acknowledged open-command execution (cmd {cmd_result.get('command_id', '')[:8]}); gate position is not sensor-verified."
    elif cmd_result.get("status") == "REJECTED":
        msg = f"Controller rejected the open command: {cmd_result.get('detail', 'command not executed')}."
    elif cmd_result.get("delivered"):
        msg = "Open command delivered, but no final controller acknowledgement was received."
    else:
        msg = f"Manual gate open failed: {cmd_result.get('error', 'unknown')}"

    return ManualCommandResponse(
        accepted=cmd_result.get("delivered", False),
        command_type="MANUAL_GATE_OPEN",
        command_result=CommandResult(
            success=cmd_result.get("success", False),
            delivered=cmd_result.get("delivered", False),
            controller_acknowledged=cmd_result.get("controller_acknowledged", False),
            physical_position_confirmed=False,
            command_id=cmd_result.get("command_id"),
            status=cmd_result.get("status", "UNKNOWN"),
            detail=cmd_result.get("detail"),
            error=cmd_result.get("error"),
        ),
        message=msg,
    )


@router.post("/gate/manual-close", response_model=ManualCommandResponse)
async def manual_gate_close(
    body: ManualCloseRequest,
    operator: Annotated[dict, Depends(require_operator_secret)],
):
    """
    Authorized operator manually closes the gate.
    Clears any active manual-open latch and closes the gate immediately.
    """
    operator_id = operator.get("operator_id", "unknown")

    device_manager.record_event(
        "INFO", "OPERATOR",
        "MANUAL_CLOSE_REQUESTED" if body.command_type == "MANUAL" else "OPERATOR_RESET_REQUESTED",
        f"Operator gate close requested by operator={operator_id}: {body.reason}",
        {"operator_id": operator_id, "reason": body.reason},
    )

    cmd_result = await device_manager.send_gate_close(
        command_type=body.command_type,
        reason=(
            "MANUAL_OPERATOR_CLOSE"
            if body.command_type == "MANUAL"
            else "OPERATOR_RESET"
        ),
        line1="GATE CLOSED",
        line2="SYSTEM READY",
        command_issued_at_ns=body.command_issued_at_ns,
    )

    if cmd_result.get("success"):
        msg = f"Controller acknowledged close-command execution (cmd {cmd_result.get('command_id', '')[:8]}); gate position is not sensor-verified."
    elif cmd_result.get("status") == "REJECTED":
        msg = f"Controller rejected the close command: {cmd_result.get('detail', 'command not executed')}."
    elif cmd_result.get("delivered"):
        msg = "Close command delivered, but no final controller acknowledgement was received."
    else:
        msg = f"Manual gate close failed: {cmd_result.get('error', 'unknown')}"

    return ManualCommandResponse(
        accepted=cmd_result.get("delivered", False),
        command_type=(
            "MANUAL_GATE_CLOSE"
            if body.command_type == "MANUAL"
            else "GATE_CLOSE"
        ),
        command_result=CommandResult(
            success=cmd_result.get("success", False),
            delivered=cmd_result.get("delivered", False),
            controller_acknowledged=cmd_result.get("controller_acknowledged", False),
            physical_position_confirmed=False,
            command_id=cmd_result.get("command_id"),
            status=cmd_result.get("status", "UNKNOWN"),
            detail=cmd_result.get("detail"),
            error=cmd_result.get("error"),
        ),
        message=msg,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard WebSocket (browser real-time telemetry)
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/monitor")
async def websocket_dashboard(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Dashboard WebSocket. Clients receive live STATUS_UPDATE and EVENT messages.
    The token query param is the IoT service secret (used by the HTML dashboard).
    For production, replace with a proper JWT or short-lived token.
    """
    # Allow both service-secret and any token for the simple HTML dashboard
    # In production replace with proper dashboard JWT auth
    await websocket.accept()
    device_manager.register_dashboard(websocket)

    # Send initial snapshot
    try:
        await websocket.send_json({
            "type": "INIT",
            "status": device_manager.get_status(),
            "events": device_manager.get_recent_events(),
        })
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        device_manager.unregister_dashboard(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# ESP32 Device WebSocket
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/iot/gate")
async def websocket_esp32_device(
    websocket: WebSocket,
    device_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    """
    Dedicated bidirectional WebSocket for the physical ESP32 gate controller.
    The ESP32 authenticates with device_id + token query params or an AUTH frame.
    """
    headers = websocket.headers
    dev_id = device_id or headers.get("x-device-id")
    dev_token = token or headers.get("x-device-token")
    await device_manager.handle_device_connection(websocket, device_id=dev_id, token=dev_token)
