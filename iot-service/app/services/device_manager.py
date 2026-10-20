"""
SmartGuard AI — IoT Device Manager
Single authoritative service managing the ESP32 WebSocket connection lifecycle,
command dispatch, acknowledgement tracking, heartbeat monitoring, and event telemetry.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.schemas.gate_status import (
    DeviceAuthPayload,
    DeviceCommandAckPayload,
    DeviceGateStatePayload,
    DeviceHeartbeatPayload,
    DeviceStatusSnapshot,
    DisplayStatusCommand,
    GateCloseCommand,
    GateOpenCommand,
    IoTSystemEvent,
)

logger = logging.getLogger("iot.device_manager")


class DeviceManager:
    """
    Singleton managing one ESP32 gate controller WebSocket connection.

    Responsibilities:
      - Connection authentication and lifecycle
      - Outgoing command dispatch (GATE_OPEN, GATE_CLOSE, DISPLAY_STATUS)
      - Incoming ACK resolution via asyncio.Future
      - Heartbeat watchdog
      - State tracking (requested vs reported vs confirmed)
      - In-memory bounded event log
      - Real-time broadcast to connected dashboard WebSocket clients

    State model:
      _requested_status: last status we were asked to apply (GATE_OPEN | MANUAL_REVIEW | GATE_CLOSED)
      _reported_gate_state: last state the ESP32 told us it is in
      _last_command_id: ID of the most recently dispatched command
      _last_ack_status: ACK status of the most recent command
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        # ── Device connection ──────────────────────────────────────────────
        self._device_ws: Optional[WebSocket] = None
        self._device_id: Optional[str] = None
        self._connected: bool = False
        self._connected_at: Optional[datetime] = None
        self._client_ip: Optional[str] = None
        self._last_heartbeat_at: Optional[datetime] = None

        # ── State tracking ────────────────────────────────────────────────
        self._requested_status: Optional[str] = None          # what was asked
        self._reported_gate_state: str = "UNKNOWN"            # what ESP32 said
        self._reported_gate_mode: str = "UNKNOWN"
        self._last_command_id: Optional[str] = None
        self._last_command_type: Optional[str] = None
        self._last_ack_status: Optional[str] = None
        self._uptime_seconds: Optional[int] = None
        self._wifi_rssi: Optional[int] = None
        self._free_heap: Optional[int] = None

        # ── Command deduplication (event_id cache, maxlen=500) ────────────
        self._processed_event_ids: deque[str] = deque(maxlen=500)

        # ── ACK futures: command_id -> Future ─────────────────────────────
        self._pending_acks: dict[str, asyncio.Future] = {}
        self._command_sequence = 0
        self._latest_command_sequence = 0
        self._latest_command_issued_at_ns = 0
        self._command_send_lock = asyncio.Lock()

        # ── In-memory event buffer (latest 100) ───────────────────────────
        self._event_buffer: deque[dict] = deque(maxlen=100)

        # ── Dashboard subscribers ─────────────────────────────────────────
        self._dashboard_subs: Set[WebSocket] = set()

        # ── Watchdog task ─────────────────────────────────────────────────
        self._watchdog_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Loop access ────────────────────────────────────────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        if self._loop and self._loop.is_running():
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    # ── Event logging ──────────────────────────────────────────────────────

    def record_event(
        self,
        level: str,
        source: str,
        event_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> dict:
        event = IoTSystemEvent(
            id=str(uuid.uuid4())[:8],
            level=level,        # type: ignore[arg-type]
            source=source,      # type: ignore[arg-type]
            event_type=event_type,
            message=message,
            details=details,
        )
        event_dict = event.model_dump(mode="json")
        self._event_buffer.append(event_dict)

        # Async broadcast to dashboards
        loop = self._get_loop()
        if loop and loop.is_running():
            try:
                if asyncio.get_running_loop() is loop:
                    asyncio.create_task(self._broadcast({"type": "EVENT", "data": event_dict}))
                else:
                    asyncio.run_coroutine_threadsafe(
                        self._broadcast({"type": "EVENT", "data": event_dict}), loop
                    )
            except RuntimeError:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast({"type": "EVENT", "data": event_dict}), loop
                )

        # Console log
        msg = f"[{source}] {event_type}: {message}"
        if level == "ERROR":
            logger.error(msg)
        elif level == "WARNING":
            logger.warning(msg)
        else:
            logger.info(msg)

        return event_dict

    def get_recent_events(self) -> list[dict]:
        return list(self._event_buffer)

    # ── Dashboard subscribers ──────────────────────────────────────────────

    def register_dashboard(self, ws: WebSocket) -> None:
        self._dashboard_subs.add(ws)

    def unregister_dashboard(self, ws: WebSocket) -> None:
        self._dashboard_subs.discard(ws)

    async def _broadcast(self, payload: dict) -> None:
        """Broadcast a payload dict to all connected dashboard clients."""
        if not self._dashboard_subs:
            return
        raw = json.dumps(payload)
        stale: list[WebSocket] = []
        for ws in list(self._dashboard_subs):
            try:
                await ws.send_text(raw)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._dashboard_subs.discard(ws)

    async def broadcast_status(self) -> None:
        """Push the current device status snapshot to all dashboard clients."""
        await self._broadcast({"type": "STATUS_UPDATE", "status": self.get_status()})

    # ── Device status ──────────────────────────────────────────────────────

    def get_status(self) -> dict:
        now = datetime.now(timezone.utc)
        age = (
            (now - self._last_heartbeat_at).total_seconds()
            if self._last_heartbeat_at
            else None
        )
        is_healthy = (
            self._connected
            and age is not None
            and age <= self.settings.iot_heartbeat_timeout_seconds
        )
        snap = DeviceStatusSnapshot(
            is_connected=self._connected,
            is_healthy=is_healthy,
            device_id=self._device_id,
            client_ip=self._client_ip,
            connected_at=self._connected_at.isoformat() if self._connected_at else None,
            last_heartbeat_at=self._last_heartbeat_at.isoformat() if self._last_heartbeat_at else None,
            heartbeat_age_seconds=round(age, 1) if age is not None else None,
            reported_gate_state=self._reported_gate_state,
            reported_gate_mode=self._reported_gate_mode,
            last_requested_status=self._requested_status,
            last_command_id=self._last_command_id,
            last_command_type=self._last_command_type,
            last_ack_status=self._last_ack_status,
            configured_device_id=self.settings.iot_device_id,
            auto_close_duration_ms=self.settings.iot_auto_close_duration_ms,
            uptime_seconds=self._uptime_seconds,
            wifi_rssi=self._wifi_rssi,
            free_heap=self._free_heap,
        )
        return snap.model_dump(mode="json")

    # ── Authentication ─────────────────────────────────────────────────────

    def authenticate_device(self, device_id: str, token: str) -> bool:
        return (
            device_id == self.settings.iot_device_id
            and bool(token)
            and token == self.settings.iot_device_key
        )

    # ── Connection lifecycle ───────────────────────────────────────────────

    async def handle_device_connection(
        self,
        websocket: WebSocket,
        device_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> None:
        """
        Manage one ESP32 WebSocket session.
        Accepts → authenticates → message loop → cleanup.
        """
        self._loop = asyncio.get_running_loop()
        client_ip = websocket.client.host if websocket.client else "unknown"

        # Authenticate via query params, or wait for AUTH frame
        authenticated = bool(device_id and token and self.authenticate_device(device_id, token))

        if not authenticated:
            await websocket.accept()
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                auth_data = DeviceAuthPayload.model_validate(json.loads(raw))
                device_id = auth_data.device_id
                if not self.authenticate_device(auth_data.device_id, auth_data.token):
                    self.record_event(
                        "ERROR", "SYSTEM", "AUTH_FAILED",
                        f"Device authentication failed from {client_ip}",
                        {"client_ip": client_ip},
                    )
                    await websocket.close(code=1008, reason="Unauthorized device credentials")
                    return
                authenticated = True
            except Exception as exc:
                self.record_event(
                    "ERROR", "SYSTEM", "AUTH_TIMEOUT",
                    f"Authentication handshake failed from {client_ip}: {exc}",
                )
                await websocket.close(code=1008, reason="Authentication handshake timeout")
                return
        else:
            await websocket.accept()

        # Supersede any existing connection for the same device
        if self._device_ws and self._device_ws is not websocket:
            try:
                await self._device_ws.close(code=1000, reason="Superseded by new connection")
            except Exception:
                pass
            self._cleanup_device(self._device_ws)

        now = datetime.now(timezone.utc)
        self._device_ws = websocket
        self._device_id = device_id
        self._connected = True
        self._connected_at = now
        self._last_heartbeat_at = now
        self._client_ip = client_ip
        self._reported_gate_state = "UNKNOWN"   # do NOT assume CLOSED on reconnect
        self._reported_gate_mode = "UNKNOWN"

        self.record_event(
            "SUCCESS", "ESP32", "DEVICE_CONNECTED",
            f"Controller '{device_id}' connected from {client_ip}",
            {"device_id": device_id, "ip": client_ip},
        )
        await self.broadcast_status()

        # Ensure watchdog is running
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._heartbeat_watchdog())

        # Message receive loop
        try:
            while True:
                raw = await websocket.receive_text()
                if self._device_ws is websocket:
                    await self._process_incoming(raw)
        except WebSocketDisconnect:
            self.record_event(
                "WARNING", "ESP32", "DEVICE_DISCONNECTED",
                f"Controller '{self._device_id}' disconnected",
            )
        except Exception as exc:
            self.record_event(
                "ERROR", "ESP32", "CONNECTION_ERROR",
                f"Controller connection error: {type(exc).__name__}: {exc}",
            )
        finally:
            self._cleanup_device(websocket)

    def _cleanup_device(self, websocket: Optional[WebSocket] = None) -> None:
        """Reset all connection flags and fail pending ACK futures."""
        if websocket is not None and self._device_ws is not websocket:
            return
        self._connected = False
        self._device_ws = None
        self._connected_at = None

        # NOTE: do NOT reset _reported_gate_state to CLOSED. It is now UNKNOWN.
        self._reported_gate_state = "UNKNOWN"
        self._reported_gate_mode = "UNKNOWN"

        # Fail pending ACKs
        for cid, fut in list(self._pending_acks.items()):
            if not fut.done():
                fut.set_result({"status": "FAILED", "error": "DEVICE_DISCONNECTED", "command_id": cid})
        self._pending_acks.clear()

        loop = self._get_loop()
        if loop and loop.is_running():
            try:
                if asyncio.get_running_loop() is loop:
                    asyncio.create_task(self.broadcast_status())
                else:
                    asyncio.run_coroutine_threadsafe(self.broadcast_status(), loop)
            except RuntimeError:
                asyncio.run_coroutine_threadsafe(self.broadcast_status(), loop)

    # ── Heartbeat watchdog ─────────────────────────────────────────────────

    async def _heartbeat_watchdog(self) -> None:
        """Periodically checks heartbeat freshness. Closes stale connections."""
        while True:
            await asyncio.sleep(5.0)
            if not self._connected or not self._last_heartbeat_at:
                if not self._connected:
                    break  # Device gone; stop watchdog task
                continue

            age = (datetime.now(timezone.utc) - self._last_heartbeat_at).total_seconds()
            if age > self.settings.iot_heartbeat_timeout_seconds:
                self.record_event(
                    "WARNING", "SYSTEM", "HEARTBEAT_TIMEOUT",
                    f"No heartbeat for {round(age, 1)}s from '{self._device_id}'. Closing stale connection.",
                    {"age_seconds": round(age, 1)},
                )
                stale_ws = self._device_ws
                if stale_ws:
                    try:
                        await stale_ws.close(code=1001, reason="Heartbeat timeout")
                    except Exception:
                        pass
                self._cleanup_device(stale_ws)
                break  # cleanup will reset state; exit this watchdog iteration

    # ── Incoming message router ────────────────────────────────────────────

    async def _process_incoming(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            self.record_event("ERROR", "ESP32", "INVALID_JSON", "Received malformed JSON frame")
            return

        msg_type = data.get("type")

        if msg_type == "HEARTBEAT":
            try:
                hb = DeviceHeartbeatPayload.model_validate(data)
                self._last_heartbeat_at = datetime.now(timezone.utc)
                self._reported_gate_state = hb.state
                self._reported_gate_mode = hb.gate_mode
                self._uptime_seconds = hb.uptime_seconds
                self._wifi_rssi = hb.wifi_rssi
                self._free_heap = hb.free_heap
                self.record_event(
                    "INFO", "ESP32", "HEARTBEAT_RECEIVED",
                    f"Heartbeat: gate={hb.state}, mode={hb.gate_mode}, uptime={hb.uptime_seconds}s, RSSI={hb.wifi_rssi}dBm",
                    {"state": hb.state, "gate_mode": hb.gate_mode, "uptime": hb.uptime_seconds, "rssi": hb.wifi_rssi},
                )
            except Exception as e:
                self.record_event("WARNING", "ESP32", "MALFORMED_HEARTBEAT", f"Invalid heartbeat: {e}")

        elif msg_type in ("COMMAND_ACK", "GATE_ACTION_ACK"):
            try:
                ack = DeviceCommandAckPayload.model_validate(data)
                cid = ack.command_id
                self._last_ack_status = ack.status
                final_status = ack.status in {"EXECUTED", "COMPLETED", "REJECTED", "FAILED"}
                successful = ack.status in {"EXECUTED", "COMPLETED"}
                self.record_event(
                    "SUCCESS" if successful else "INFO" if ack.status == "ACCEPTED" else "WARNING",
                    "ESP32", "COMMAND_ACK",
                    f"Command {cid[:8]} → {ack.status}" + (f" ({ack.detail})" if ack.detail else ""),
                    {"command_id": cid, "status": ack.status},
                )
                # Only resolve future if it belongs to the current active command
                if final_status:
                    fut = self._pending_acks.pop(cid, None)
                    if fut and not fut.done():
                        fut.set_result(ack.model_dump())
                await self.broadcast_status()
            except Exception as e:
                self.record_event("WARNING", "ESP32", "MALFORMED_ACK", f"Invalid ACK: {e}")

        elif msg_type == "GATE_STATE":
            try:
                gs = DeviceGateStatePayload.model_validate(data)
                self._reported_gate_state = gs.state
                self._reported_gate_mode = gs.gate_mode
                self.record_event(
                    "INFO", "ESP32", "GATE_STATE_REPORTED",
                    f"Physical gate state: {gs.state}, mode={gs.gate_mode}" + (f" (cmd {gs.command_id[:8]})" if gs.command_id else ""),
                    {"state": gs.state, "gate_mode": gs.gate_mode, "command_id": gs.command_id},
                )
                await self.broadcast_status()
            except Exception as e:
                self.record_event("WARNING", "ESP32", "MALFORMED_GATE_STATE", f"Invalid state report: {e}")

        else:
            self.record_event("WARNING", "ESP32", "UNKNOWN_TYPE", f"Unrecognised packet type: {msg_type}")

    # ── Outgoing commands ──────────────────────────────────────────────────

    async def send_gate_open(
        self,
        command_type: str = "AUTOMATED",
        attempt_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        line1: str = "GATE OPEN",
        line2: str = "WELCOME",
        command_issued_at_ns: Optional[int] = None,
    ) -> dict:
        """Send GATE_OPEN and wait for a final controller acknowledgement."""
        command_sequence = self._next_command_sequence(command_issued_at_ns)
        if command_sequence is None:
            return {"success": False, "delivered": False, "error": "SUPERSEDED", "status": "REJECTED"}
        command_id = str(uuid.uuid4())
        cmd_duration = duration_ms or self.settings.iot_auto_close_duration_ms

        cmd = GateOpenCommand(
            command_id=command_id,
            command_sequence=command_sequence,
            command_type=command_type,
            attempt_id=attempt_id,
            duration_ms=cmd_duration,
            line1=line1[:16],
            line2=line2[:16],
        )

        ack_future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_acks[command_id] = ack_future
        self._last_command_id = command_id
        self._last_command_type = command_type

        try:
            async with self._command_send_lock:
                if command_sequence < self._latest_command_sequence:
                    self._pending_acks.pop(command_id, None)
                    return {"success": False, "error": "SUPERSEDED", "status": "REJECTED"}
                if not self._connected or not self._device_ws:
                    self._pending_acks.pop(command_id, None)
                    return {"success": False, "error": "DEVICE_OFFLINE", "status": "FAILED"}
                await self._device_ws.send_text(cmd.model_dump_json())
            self.record_event(
                "INFO", "SYSTEM", "GATE_OPEN_SENT",
                f"Sent GATE_OPEN {command_id[:8]} ({command_type}, {cmd_duration}ms)",
                {"command_id": command_id, "attempt_id": attempt_id, "type": command_type},
            )

            ack_timeout = self.settings.iot_ack_timeout_seconds
            ack_response = await asyncio.wait_for(ack_future, timeout=ack_timeout)
            is_accepted = ack_response.get("status") in ("EXECUTED", "COMPLETED")
            self._last_ack_status = ack_response.get("status")
            return {
                "success": is_accepted,
                "delivered": True,
                "controller_acknowledged": is_accepted,
                "physical_position_confirmed": False,
                "command_id": command_id,
                "status": ack_response.get("status"),
                "detail": ack_response.get("detail"),
            }

        except asyncio.TimeoutError:
            self._pending_acks.pop(command_id, None)
            self.record_event(
                "ERROR", "SYSTEM", "ACK_TIMEOUT",
                f"GATE_OPEN {command_id[:8]} timed out waiting for ESP32 ACK",
            )
            return {
                "success": False,
                "delivered": True,
                "controller_acknowledged": False,
                "physical_position_confirmed": False,
                "command_id": command_id,
                "error": "ACK_TIMEOUT",
                "status": "FAILED",
            }
        except Exception as exc:
            self._pending_acks.pop(command_id, None)
            self.record_event("ERROR", "SYSTEM", "COMMAND_EXCEPTION", f"GATE_OPEN error: {exc}")
            return {"success": False, "error": str(exc), "status": "FAILED"}

    async def send_gate_close(
        self,
        command_type: str = "AUTOMATED",
        reason: str = "GATE_CLOSED",
        line1: str = "GATE CLOSED",
        line2: str = "PLEASE WAIT",
        command_issued_at_ns: Optional[int] = None,
    ) -> dict:
        """Send GATE_CLOSE and wait for a final controller acknowledgement."""
        command_sequence = self._next_command_sequence(command_issued_at_ns)
        if command_sequence is None:
            return {"success": False, "delivered": False, "error": "SUPERSEDED", "status": "REJECTED"}
        command_id = str(uuid.uuid4())
        cmd = GateCloseCommand(
            command_id=command_id,
            command_sequence=command_sequence,
            command_type=command_type,
            reason=reason[:64],
            line1=line1[:16],
            line2=line2[:16],
        )

        ack_future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_acks[command_id] = ack_future
        self._last_command_id = command_id
        self._last_command_type = command_type

        try:
            async with self._command_send_lock:
                if command_sequence < self._latest_command_sequence:
                    self._pending_acks.pop(command_id, None)
                    return {"success": False, "error": "SUPERSEDED", "status": "REJECTED"}
                if not self._connected or not self._device_ws:
                    self._pending_acks.pop(command_id, None)
                    return {"success": False, "error": "DEVICE_OFFLINE", "status": "FAILED"}
                await self._device_ws.send_text(cmd.model_dump_json())
            self.record_event(
                "INFO", "SYSTEM", "GATE_CLOSE_SENT",
                f"Sent GATE_CLOSE {command_id[:8]} ({command_type}, reason={reason})",
                {"command_id": command_id, "reason": reason, "type": command_type},
            )

            ack_timeout = self.settings.iot_ack_timeout_seconds
            ack_response = await asyncio.wait_for(ack_future, timeout=ack_timeout)
            is_accepted = ack_response.get("status") in ("EXECUTED", "COMPLETED")
            self._last_ack_status = ack_response.get("status")
            return {
                "success": is_accepted,
                "delivered": True,
                "controller_acknowledged": is_accepted,
                "physical_position_confirmed": False,
                "command_id": command_id,
                "status": ack_response.get("status"),
                "detail": ack_response.get("detail"),
            }

        except asyncio.TimeoutError:
            self._pending_acks.pop(command_id, None)
            self.record_event(
                "ERROR", "SYSTEM", "ACK_TIMEOUT",
                f"GATE_CLOSE {command_id[:8]} timed out waiting for ESP32 ACK",
            )
            return {
                "success": False,
                "delivered": True,
                "controller_acknowledged": False,
                "physical_position_confirmed": False,
                "command_id": command_id,
                "error": "ACK_TIMEOUT",
                "status": "FAILED",
            }
        except Exception as exc:
            self._pending_acks.pop(command_id, None)
            self.record_event("ERROR", "SYSTEM", "COMMAND_EXCEPTION", f"GATE_CLOSE error: {exc}")
            return {"success": False, "error": str(exc), "status": "FAILED"}

    async def send_display_status(self, line1: str, line2: str) -> dict:
        """Update LCD display only, without moving servo."""
        if not self._connected or not self._device_ws:
            return {"delivered": False, "status": "DEVICE_OFFLINE", "error": "DEVICE_OFFLINE"}
        cmd = DisplayStatusCommand(
            message_id=str(uuid.uuid4())[:8],
            line1=line1[:16],
            line2=line2[:16],
        )
        try:
            await self._device_ws.send_text(cmd.model_dump_json())
            return {"delivered": True, "status": "SENT"}
        except Exception as e:
            logger.warning("Failed to send DISPLAY_STATUS: %s", e)
            return {"delivered": False, "status": "FAILED", "error": "SEND_FAILED"}

    # ── Event ID deduplication ─────────────────────────────────────────────

    def is_duplicate_event(self, event_id: str) -> bool:
        if event_id in self._processed_event_ids:
            return True
        self._processed_event_ids.append(event_id)
        return False

    def _next_command_sequence(self, issued_at_ns: Optional[int] = None) -> Optional[int]:
        issued = issued_at_ns if issued_at_ns is not None else time.time_ns()
        if issued <= self._latest_command_issued_at_ns:
            return None
        self._latest_command_issued_at_ns = issued
        self._command_sequence += 1
        self._latest_command_sequence = self._command_sequence
        return self._command_sequence


# Global singleton
device_manager = DeviceManager()
