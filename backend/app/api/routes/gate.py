"""
SmartGuard AI — Gate Control & IoT Monitoring API Routes
Includes simulated gate controls, physical ESP32 controller commands,
and telemetry endpoints.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from app.api.dependencies import get_active_account, require_admin, require_security
from app.core.security import decode_access_token
from app.models.account import SecurityAccount
from app.schemas.access import GateStatusResponse
from app.services import gate_service
from app.services.iot_service import iot_manager

logger = logging.getLogger("smartguard.gate_api")
router = APIRouter(prefix="/gate", tags=["gate"])


@router.get("/status", response_model=GateStatusResponse)
def get_gate_status(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return the current simulated gate state and physical controller status."""
    return GateStatusResponse(**gate_service.get_status())


@router.get("/iot/status")
def get_iot_status(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return detailed physical IoT controller connection and telemetry status."""
    return iot_manager.get_status()


@router.get("/iot/events")
def get_iot_events(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return recent in-memory IoT system events for monitoring."""
    return iot_manager.get_recent_events()


@router.post("/reset")
async def reset_gate(
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Force the gate to CLOSED state (simulated and physical).
    Awaits physical controller acknowledgement if connected.
    """
    # 1. Update in-process simulated state
    logger.info("gate Force-reset initiated by officer/admin=%s", account.id)

    # 2. Command the physical ESP32 controller
    hardware_status = {
        "connected": False,
        "acknowledged": False,
        "command_id": None,
        "controller_state": "UNKNOWN",
        "error": None,
    }

    iot_status = iot_manager.get_status()
    hardware_status["connected"] = bool(iot_status.get("is_connected"))
    hw_res = await iot_manager.send_manual_gate_command(
        opened=False,
        operator_role=account.role,
        operator_id=str(account.id),
        reason="Operator reset",
        command_type="AUTOMATED",
    )
    if hw_res.get("controller_acknowledged"):
        gate_service.force_close(
            initiated_by=str(account.id),
            dispatch_hardware=False,
        )
    hardware_status["command_id"] = hw_res.get("command_id")
    hardware_status["delivered"] = hw_res.get("delivered", False)
    hardware_status["acknowledged"] = hw_res.get("controller_acknowledged", False)
    hardware_status["status"] = hw_res.get("status", "UNKNOWN")
    hardware_status["physical_position_confirmed"] = False
    hardware_status["controller_state"] = iot_manager.get_status().get(
        "reported_gate_state", "UNKNOWN"
    )
    hardware_status["error"] = hw_res.get("error")
    msg = hw_res.get("message") or (
        "Close command delivered; waiting for controller acknowledgement."
        if hardware_status["delivered"] and not hardware_status["acknowledged"]
        else "The controller acknowledged the close command; no gate-position sensor is configured."
        if hardware_status["acknowledged"]
        else "Close command failed; gate state was not changed."
    )

    # Update latest snapshot
    status_data = gate_service.get_status()

    return {
        "message": msg,
        "status": status_data,
        "hardware": hardware_status,
    }


@router.post("/open")
async def manual_open_gate(
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Manually command the gate to open (for security operators and administrators).
    Updates state and sends GATE_OPEN command to the ESP32.
    """
    logger.info("gate Manual open commanded by officer/admin=%s", account.id)

    # Only latch the backend simulation after the controller confirms the command.
    hw_res = await iot_manager.send_manual_gate_command(
        opened=True,
        operator_role=account.role,
        operator_id=str(account.id),
        reason="Manual gate open",
    )
    if hw_res.get("controller_acknowledged"):
        gate_service.latch_manual_open(str(account.id))

    status_data = gate_service.get_status()
    return {
        "message": hw_res.get("message") or (
            "Open command delivered; waiting for controller acknowledgement."
            if hw_res.get("delivered") and not hw_res.get("controller_acknowledged")
            else "The controller acknowledged the open command; no gate-position sensor is configured."
            if hw_res.get("controller_acknowledged")
            else f"Manual gate open command failed: {hw_res.get('error', 'unknown')}"
        ),
        "status": status_data,
        "hardware": hw_res,
    }


@router.post("/close")
async def manual_close_gate(
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Manually command the gate to close immediately (for security operators and administrators).
    """
    logger.info("gate Manual close commanded by officer/admin=%s", account.id)

    hw_res = await iot_manager.send_manual_gate_command(
        opened=False,
        operator_role=account.role,
        operator_id=str(account.id),
        reason="Manual gate close",
    )
    if hw_res.get("controller_acknowledged"):
        status_data = gate_service.force_close(
            initiated_by=str(account.id),
            dispatch_hardware=False,
        )
    else:
        status_data = gate_service.get_status()

    return {
        "message": hw_res.get("message") or (
            "Close command delivered; waiting for controller acknowledgement."
            if hw_res.get("delivered") and not hw_res.get("controller_acknowledged")
            else "The controller acknowledged the close command; no gate-position sensor is configured."
            if hw_res.get("controller_acknowledged")
            else f"Manual gate close command failed: {hw_res.get('error', 'unknown')}"
        ),
        "status": status_data,
        "hardware": hw_res,
    }


# ── Dashboard Monitoring WebSocket ───────────────────────────────────────────

@router.websocket("/ws/monitor")
async def websocket_dashboard_monitor(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    WebSocket channel for authenticated frontend clients to receive live
    gate and IoT system events.
    """
    # Authenticate JWT token
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(token)
        if not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid token subject")
            return
    except (JWTError, ValueError):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    iot_manager.register_dashboard(websocket)

    # Send initial snapshot immediately upon connect
    try:
        initial_payload = {
            "type": "INIT",
            "status": iot_manager.get_status(),
            "gate_status": gate_service.get_status(),
            "events": iot_manager.get_recent_events(),
        }
        await websocket.send_json(initial_payload)
    except Exception as exc:
        logger.warning("gate_api Failed to send initial payload to dashboard WS: %s", exc)

    try:
        while True:
            # Dashboard clients can send ping or keepalive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        iot_manager.unregister_dashboard(websocket)
