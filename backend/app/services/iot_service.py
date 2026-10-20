"""Authenticated bridge from the main backend to the IoT microservice."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import threading
import time
import uuid
from typing import Literal, Optional, Set

import httpx
from fastapi import WebSocket

from app.core.config import get_settings

logger = logging.getLogger("smartguard.iot")


class IoTManager:
    """Bridge gate events to the sole physical-device connection manager."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._event_buffer: deque[dict] = deque(maxlen=100)
        self._seen_microservice_event_ids: deque[str] = deque(maxlen=200)
        self._dashboard_subscribers: Set[WebSocket] = set()
        self._microservice_status: Optional[dict] = None
        self._microservice_sync_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._command_issue_lock = threading.Lock()
        self._last_command_issued_at_ns = 0

    def _next_command_issued_at_ns(self) -> int:
        with self._command_issue_lock:
            self._last_command_issued_at_ns = max(
                time.time_ns(), self._last_command_issued_at_ns + 1
            )
            return self._last_command_issued_at_ns

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if not self.settings.iot_service_secret:
            logger.error("IoT bridge disabled: configure IOT_SERVICE_SECRET in backend/.env")
        if self._microservice_sync_task is None or self._microservice_sync_task.done():
            self._microservice_sync_task = loop.create_task(self._poll_microservice())

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        if self._loop and self._loop.is_running():
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Service-Secret": self.settings.iot_service_secret,
        }

    async def _call_microservice(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
        *,
        method: str = "POST",
        headers: Optional[dict[str, str]] = None,
        log_failure: bool = True,
    ) -> dict | list:
        if not self.settings.iot_service_secret:
            return {"success": False, "error": "SERVICE_SECRET_NOT_CONFIGURED"}

        url = f"{self.settings.iot_microservice_url.rstrip('/')}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.request(
                    method,
                    url,
                    json=payload,
                    headers=headers or self._headers(),
                )
            try:
                data = response.json()
            except ValueError:
                data = {}
            if response.is_success and isinstance(data, (dict, list)):
                return data
            if log_failure:
                logger.warning("IoT microservice %s returned HTTP %s", endpoint, response.status_code)
            return {
                "success": False,
                "error": "MICROSERVICE_HTTP_ERROR",
                "http_status": response.status_code,
            }
        except httpx.HTTPError as exc:
            if log_failure:
                logger.warning(
                    "IoT microservice request failed for %s (%s)",
                    endpoint,
                    type(exc).__name__,
                )
            return {"success": False, "error": "MICROSERVICE_UNAVAILABLE"}

    async def _poll_microservice(self) -> None:
        last_error: Optional[str] = None
        while True:
            status_data = await self._call_microservice(
                "/api/v1/device/status",
                method="GET",
                log_failure=False,
            )
            if isinstance(status_data, dict) and status_data.get("is_connected") is not None:
                self._microservice_status = status_data
                from app.services import gate_service
                gate_service.sync_controller_status(status_data)
                last_error = None
                self._broadcast_status()
                events = await self._call_microservice(
                    "/api/v1/device/events",
                    method="GET",
                    log_failure=False,
                )
                if isinstance(events, list):
                    for event in events:
                        event_id = event.get("id") if isinstance(event, dict) else None
                        if not event_id or event_id in self._seen_microservice_event_ids:
                            continue
                        self._seen_microservice_event_ids.append(event_id)
                        self._event_buffer.append(event)
                        self._schedule(self._broadcast({"type": "EVENT", "data": event}))
            else:
                error = (
                    str(status_data.get("error", "MICROSERVICE_UNAVAILABLE"))
                    if isinstance(status_data, dict)
                    else "INVALID_MICROSERVICE_RESPONSE"
                )
                if self._microservice_status is not None:
                    self._microservice_status = None
                    self._broadcast_status()
                if error != last_error:
                    logger.warning("IoT status polling unavailable: %s", error)
                    last_error = error
            await asyncio.sleep(4.0)

    def record_event(
        self,
        level: str,
        source: str,
        event_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> dict:
        event = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source": source,
            "event_type": event_type,
            "message": message,
            "details": details,
        }
        self._event_buffer.append(event)
        log_message = f"[IoT {source}] {event_type}: {message}"
        if level == "ERROR":
            logger.error(log_message)
        elif level == "WARNING":
            logger.warning(log_message)
        else:
            logger.info(log_message)
        self._schedule(self._broadcast({"type": "EVENT", "data": event}))
        return event

    def get_recent_events(self) -> list[dict]:
        return list(self._event_buffer)

    def get_status(self) -> dict:
        if self._microservice_status is not None:
            return self._microservice_status
        return {
            "is_connected": False,
            "is_healthy": False,
            "device_id": None,
            "client_ip": None,
            "connected_at": None,
            "last_heartbeat_at": None,
            "heartbeat_age_seconds": None,
            "reported_gate_state": "UNKNOWN",
            "reported_gate_mode": "UNKNOWN",
            "configured_device_id": "unknown",
            "auto_close_duration_ms": self.settings.iot_auto_close_duration_ms,
        }

    async def _broadcast(self, payload: dict) -> None:
        stale: list[WebSocket] = []
        encoded = json.dumps(payload)
        for websocket in list(self._dashboard_subscribers):
            try:
                await websocket.send_text(encoded)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self._dashboard_subscribers.discard(websocket)

    def _broadcast_status(self) -> None:
        from app.services import gate_service

        self._schedule(
            self._broadcast({
                "type": "STATUS_UPDATE",
                "status": self.get_status(),
                "gate_status": gate_service.get_status(),
            })
        )

    def _schedule(self, coroutine) -> None:
        loop = self.get_loop()
        if not loop or not loop.is_running():
            coroutine.close()
            return
        try:
            if asyncio.get_running_loop() is loop:
                loop.create_task(coroutine)
            else:
                asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(coroutine, loop)

    def register_dashboard(self, websocket: WebSocket) -> None:
        self._dashboard_subscribers.add(websocket)

    def unregister_dashboard(self, websocket: WebSocket) -> None:
        self._dashboard_subscribers.discard(websocket)

    async def send_gate_open(
        self,
        attempt_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        message: str = "ACCESS GRANTED",
        command_issued_at_ns: Optional[int] = None,
    ) -> dict:
        payload = {
            "event_id": str(uuid.uuid4()),
            "status": "GATE_OPEN",
            "attempt_id": attempt_id,
            "reason": message,
            "duration_ms": duration_ms,
            "command_issued_at_ns": command_issued_at_ns or self._next_command_issued_at_ns(),
        }
        result = await self._call_microservice("/api/v1/gate/status", payload)
        return self._command_result(result)

    async def send_gate_close(self, reason: str = "GATE_CLOSED") -> dict:
        result = await self._call_microservice(
            "/api/v1/gate/status",
            {
                "event_id": str(uuid.uuid4()),
                "status": "GATE_CLOSED",
                "reason": reason,
                "command_issued_at_ns": self._next_command_issued_at_ns(),
            },
        )
        return self._command_result(result)

    async def send_manual_gate_command(
        self,
        *,
        opened: bool,
        operator_role: str,
        operator_id: str,
        reason: str,
        command_type: Literal["AUTOMATED", "MANUAL"] = "MANUAL",
    ) -> dict:
        endpoint = "/api/v1/gate/manual-open" if opened else "/api/v1/gate/manual-close"
        payload = {
            "reason": reason,
            "command_issued_at_ns": self._next_command_issued_at_ns(),
        }
        if not opened:
            payload["command_type"] = command_type
        headers = {
            **self._headers(),
            "X-Operator-Role": operator_role,
            "X-Operator-Id": operator_id,
        }
        result = await self._call_microservice(endpoint, payload, headers=headers)
        return self._command_result(result)

    @staticmethod
    def _command_result(response: dict | list) -> dict:
        if not isinstance(response, dict):
            return {
                "success": False,
                "delivered": False,
                "controller_acknowledged": False,
                "physical_position_confirmed": False,
                "error": "INVALID_MICROSERVICE_RESPONSE",
                "status": "FAILED",
            }
        command = response.get("command_result") or {}
        delivered = bool(command.get("delivered", False))
        return {
            "accepted": bool(response.get("accepted", False)),
            "success": bool(command.get("success", False)),
            "delivered": delivered,
            "controller_acknowledged": bool(command.get("controller_acknowledged", False)),
            "physical_position_confirmed": False,
            "command_id": command.get("command_id"),
            "status": command.get("status", response.get("error", "UNKNOWN")),
            "detail": command.get("detail"),
            "error": command.get("error", response.get("error")),
            "message": response.get("message"),
        }

    async def send_display_status(self, line1: str, line2: str) -> dict:
        return await self._call_microservice(
            "/api/v1/gate/display-status",
            {"line1": line1[:16], "line2": line2[:16]},
        )

    def dispatch_open_command(
        self,
        attempt_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        message: str = "ACCESS GRANTED",
    ) -> None:
        issued_at_ns = self._next_command_issued_at_ns()
        self._schedule(
            self.send_gate_open(
                attempt_id=attempt_id,
                duration_ms=duration_ms,
                message=message,
                command_issued_at_ns=issued_at_ns,
            )
        )

    def dispatch_display_status(self, line1: str, line2: str) -> None:
        self._schedule(self.send_display_status(line1, line2))


iot_manager = IoTManager()
