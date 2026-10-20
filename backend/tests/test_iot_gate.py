"""Tests for the authenticated main-backend to IoT-microservice bridge."""
import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import require_security
from app.core.security import create_access_token
from app.main import app
from app.services import gate_service
from app.services.iot_service import iot_manager


@pytest.fixture(autouse=True)
def reset_iot_state(monkeypatch):
    monkeypatch.setattr(iot_manager.settings, "iot_service_secret", "controlled-test-service-secret")
    iot_manager._microservice_status = None
    iot_manager._event_buffer.clear()
    app.dependency_overrides.clear()
    gate_service.force_close("test-fixture", dispatch_hardware=False)
    yield
    app.dependency_overrides.clear()


def test_backend_uses_service_secret_header_for_microservice_calls(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {"accepted": True}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, *, json, headers):
            captured.update(method=method, url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setattr("app.services.iot_service.httpx.AsyncClient", FakeAsyncClient)
    result = asyncio.run(iot_manager._call_microservice(
        "/api/v1/gate/status",
        {"status": "GATE_OPEN"},
    ))
    asyncio.run(iot_manager.send_manual_gate_command(
        opened=False,
        operator_role="SECURITY",
        operator_id="controlled-test-operator",
        reason="controlled test",
    ))

    assert result == {"accepted": True}
    assert captured["headers"]["X-Service-Secret"] == "controlled-test-service-secret"
    assert captured["headers"]["X-Operator-Role"] == "SECURITY"
    assert captured["headers"]["X-Operator-Id"] == "controlled-test-operator"
    assert captured["url"].endswith("/api/v1/gate/manual-close")
    assert captured["json"]["command_type"] == "MANUAL"


def test_manual_gate_open_forwards_validated_operator_identity(monkeypatch):
    account = MagicMock()
    account.id = uuid.uuid4()
    account.role = "SECURITY"
    app.dependency_overrides[require_security] = lambda: account

    send_manual = AsyncMock(return_value={
        "accepted": True,
        "success": True,
        "delivered": True,
        "controller_acknowledged": True,
        "physical_position_confirmed": False,
        "command_id": "command-1",
        "status": "EXECUTED",
        "detail": "Servo target set; no position sensor",
        "error": None,
        "message": "Controller acknowledged; gate position is not sensor-verified.",
    })
    monkeypatch.setattr(iot_manager, "send_manual_gate_command", send_manual)

    response = TestClient(app).post("/api/gate/open")

    assert response.status_code == 200
    send_manual.assert_awaited_once_with(
        opened=True,
        operator_role="SECURITY",
        operator_id=str(account.id),
        reason="Manual gate open",
    )
    data = response.json()
    assert data["hardware"]["delivered"] is True
    assert data["hardware"]["controller_acknowledged"] is True
    assert data["hardware"]["physical_position_confirmed"] is False
    assert data["status"]["state"] == "MANUAL_LATCHED_OPEN"
    assert "not sensor-verified" in data["message"]


def test_backend_no_longer_registers_physical_device_websocket():
    assert not any(route.path == "/ws/iot/gate" for route in app.routes)
    assert any(route.path == "/ws/gate/monitor" for route in app.routes)


def test_old_simulated_auto_close_timer_cannot_close_a_newer_open():
    gate_service.apply_decision(
        "ALLOW",
        "ENTRY",
        "old-open",
        open_duration_seconds=3600,
        dispatch_hardware=False,
    )
    old_generation = gate_service._gate_generation
    gate_service.force_close("manual-close", dispatch_hardware=False)
    gate_service.apply_decision(
        "ALLOW",
        "ENTRY",
        "new-open",
        open_duration_seconds=3600,
        dispatch_hardware=False,
    )

    gate_service._auto_close_callback(old_generation)

    assert gate_service.get_status()["state"] == "OPEN"
    gate_service.force_close("test-cleanup", dispatch_hardware=False)


def test_automated_gate_open_defaults_to_fifteen_seconds(monkeypatch):
    dispatched = {}
    monkeypatch.setattr(
        iot_manager,
        "dispatch_open_command",
        lambda **kwargs: dispatched.update(kwargs),
    )

    gate_service.apply_decision("ALLOW", "ENTRY", "test-fifteen-second-open")

    assert gate_service.get_status()["state"] == "OPEN"
    assert dispatched["duration_ms"] == 15000
    gate_service.force_close("test-cleanup", dispatch_hardware=False)


def test_automated_decisions_cannot_change_manual_latched_gate(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        iot_manager,
        "dispatch_open_command",
        lambda **kwargs: dispatched.append(("open", kwargs)),
    )
    monkeypatch.setattr(
        iot_manager,
        "dispatch_display_status",
        lambda *args: dispatched.append(("display", args)),
    )
    gate_service.latch_manual_open("test-operator")

    result = gate_service.apply_decision("DENY", "ENTRY", "denied-attempt")

    assert result == "MANUAL_LATCHED_OPEN"
    assert gate_service.get_status()["state"] == "MANUAL_LATCHED_OPEN"
    assert dispatched == []
    gate_service.force_close("test-cleanup", dispatch_hardware=False)


def test_controller_startup_closed_report_clears_only_an_older_manual_latch():
    gate_service.latch_manual_open("test-operator")
    latch_time = gate_service._manual_latched_at
    assert latch_time is not None

    gate_service.sync_controller_status({
        "reported_gate_state": "CLOSED",
        "reported_gate_mode": "AUTOMATED",
        "last_heartbeat_at": (latch_time - timedelta(seconds=1)).isoformat(),
    })
    assert gate_service.get_status()["state"] == "MANUAL_LATCHED_OPEN"

    gate_service.sync_controller_status({
        "reported_gate_state": "CLOSED",
        "reported_gate_mode": "AUTOMATED",
        "last_heartbeat_at": (latch_time + timedelta(seconds=1)).isoformat(),
    })
    assert gate_service.get_status()["state"] == "CLOSED"


def test_manual_open_is_not_latched_if_controller_does_not_acknowledge(monkeypatch):
    account = MagicMock()
    account.id = uuid.uuid4()
    account.role = "SECURITY"
    app.dependency_overrides[require_security] = lambda: account
    monkeypatch.setattr(
        iot_manager,
        "send_manual_gate_command",
        AsyncMock(return_value={
            "success": False,
            "delivered": True,
            "controller_acknowledged": False,
            "physical_position_confirmed": False,
            "status": "FAILED",
            "error": "ACK_TIMEOUT",
        }),
    )

    response = TestClient(app).post("/api/gate/open")

    assert response.status_code == 200
    assert response.json()["status"]["state"] == "CLOSED"


def test_manual_close_clears_backend_latch_only_after_controller_ack(monkeypatch):
    account = MagicMock()
    account.id = uuid.uuid4()
    account.role = "SECURITY"
    app.dependency_overrides[require_security] = lambda: account
    gate_service.latch_manual_open("test-operator")
    send_manual = AsyncMock(return_value={
        "success": True,
        "delivered": True,
        "controller_acknowledged": True,
        "physical_position_confirmed": False,
        "status": "EXECUTED",
    })
    monkeypatch.setattr(iot_manager, "send_manual_gate_command", send_manual)

    response = TestClient(app).post("/api/gate/close")

    assert response.status_code == 200
    assert response.json()["status"]["state"] == "CLOSED"
    send_manual.assert_awaited_once_with(
        opened=False,
        operator_role="SECURITY",
        operator_id=str(account.id),
        reason="Manual gate close",
    )


def test_reset_is_not_allowed_to_release_manual_latch(monkeypatch):
    account = MagicMock()
    account.id = uuid.uuid4()
    account.role = "SECURITY"
    app.dependency_overrides[require_security] = lambda: account
    gate_service.latch_manual_open("test-operator")
    send_manual = AsyncMock(return_value={
        "success": False,
        "delivered": True,
        "controller_acknowledged": False,
        "physical_position_confirmed": False,
        "status": "REJECTED",
        "error": "MANUAL_LATCH_ACTIVE",
    })
    monkeypatch.setattr(iot_manager, "send_manual_gate_command", send_manual)

    response = TestClient(app).post("/api/gate/reset")

    assert response.status_code == 200
    assert response.json()["status"]["state"] == "MANUAL_LATCHED_OPEN"
    send_manual.assert_awaited_once_with(
        opened=False,
        operator_role="SECURITY",
        operator_id=str(account.id),
        reason="Operator reset",
        command_type="AUTOMATED",
    )


def test_dashboard_monitor_websocket_remains_authenticated_and_available():
    user_id = str(uuid.uuid4())
    valid_jwt = create_access_token(
        subject=user_id,
        extra_claims={"role": "SECURITY", "email": "officer@smartguard.local"},
    )

    with TestClient(app).websocket_connect(f"/ws/gate/monitor?token={valid_jwt}") as websocket:
        initial_frame = websocket.receive_json()
        assert initial_frame["type"] == "INIT"
        assert "status" in initial_frame
        assert "gate_status" in initial_frame
        assert "events" in initial_frame
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"


def test_dashboard_monitor_status_updates_include_gate_state(monkeypatch):
    captured = []

    async def capture_broadcast(payload):
        captured.append(payload)

    def run_scheduled(coroutine):
        asyncio.run(coroutine)

    monkeypatch.setattr(iot_manager, "_microservice_status", {
        "is_connected": True,
        "reported_gate_state": "OPEN",
        "reported_gate_mode": "AUTOMATED",
    })
    monkeypatch.setattr(iot_manager, "_broadcast", capture_broadcast)
    monkeypatch.setattr(iot_manager, "_schedule", run_scheduled)

    iot_manager._broadcast_status()

    assert captured[0]["type"] == "STATUS_UPDATE"
    assert captured[0]["gate_status"]["state"] == gate_service.get_status()["state"]
