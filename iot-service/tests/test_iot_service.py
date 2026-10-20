"""
SmartGuard AI — IoT Microservice Test Suite
Tests covering:
  - Health & status endpoints
  - Service secret security validation
  - Operator manual command access control
  - Automated gate status & idempotency
  - WebSocket device connection & heartbeat
  - Event telemetry
"""
import asyncio
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.schemas.gate_status import GateOpenCommand
from app.services.device_manager import device_manager

settings = get_settings()
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_device_manager(monkeypatch):
    """Reset device manager state between tests."""
    monkeypatch.setattr(settings, "iot_service_secret", "test-only-service-secret-1234567890")
    monkeypatch.setattr(settings, "iot_device_key", "test-only-device-token")
    monkeypatch.setattr(settings, "iot_device_id", "test-device")
    device_manager._connected = False
    device_manager._device_ws = None
    device_manager._device_id = None
    device_manager._reported_gate_state = "UNKNOWN"
    device_manager._reported_gate_mode = "UNKNOWN"
    device_manager._pending_acks.clear()
    device_manager._processed_event_ids.clear()
    device_manager._event_buffer.clear()
    device_manager._command_sequence = 0
    device_manager._latest_command_sequence = 0
    device_manager._latest_command_issued_at_ns = 0
    yield


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "device_connected" in data
    assert "device_healthy" in data


def test_device_status_endpoint():
    response = client.get(
        "/api/v1/device/status",
        headers={"X-Service-Secret": "test-only-service-secret-1234567890"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "is_connected" in data
    assert "is_healthy" in data
    assert "reported_gate_state" in data
    assert data["is_connected"] is False


def test_gate_open_command_defaults_to_fifteen_seconds():
    command = GateOpenCommand(command_id="test-open", command_sequence=1)
    assert command.duration_ms == 15000


def test_gate_open_dispatch_uses_fifteen_second_service_setting(monkeypatch):
    async def exercise_command():
        monkeypatch.setattr(settings, "iot_auto_close_duration_ms", 15000)

        class FakeDeviceWebSocket:
            async def send_text(self, payload):
                command = json.loads(payload)
                assert command["duration_ms"] == 15000
                await device_manager._process_incoming(json.dumps({
                    "type": "COMMAND_ACK",
                    "command_id": command["command_id"],
                    "status": "EXECUTED",
                }))

        device_manager._connected = True
        device_manager._device_ws = FakeDeviceWebSocket()
        result = await device_manager.send_gate_open()
        assert result["controller_acknowledged"] is True

    asyncio.run(exercise_command())


def test_manual_gate_open_dispatch_carries_manual_command_type(monkeypatch):
    async def exercise_command():
        captured = {}

        class FakeDeviceWebSocket:
            async def send_text(self, payload):
                command = json.loads(payload)
                captured.update(command)
                await device_manager._process_incoming(json.dumps({
                    "type": "COMMAND_ACK",
                    "command_id": command["command_id"],
                    "status": "EXECUTED",
                }))

        device_manager._connected = True
        device_manager._device_ws = FakeDeviceWebSocket()
        result = await device_manager.send_gate_open(
            command_type="MANUAL",
            line1="MANUAL GATE OPEN",
            line2="WAITING TO CLOSE",
        )

        assert result["controller_acknowledged"] is True
        assert captured["command_type"] == "MANUAL"
        assert captured["line1"] == "MANUAL GATE OPEN"
        assert captured["line2"] == "WAITING TO CLOSE"
        assert captured["duration_ms"] == 15000

    asyncio.run(exercise_command())


def test_manual_open_dispatch_is_marked_manual_and_never_arms_timer(monkeypatch):
    from scripts.mock_esp32 import MockEsp32Controller

    async def exercise_manual_latch():
        simulator = MockEsp32Controller(
            "ws://127.0.0.1:8001/api/v1/ws/iot/gate",
            "test-device",
            "test-only-device-token",
        )

        async def capture_json(payload):
            simulator.sent_packets.append(payload)

        simulator.sent_packets = []
        simulator.send_json = capture_json
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "automated-open",
            "command_sequence": 1,
            "command_type": "AUTOMATED",
            "duration_ms": 30,
        }))
        assert simulator.auto_close_task is not None

        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "manual-open",
            "command_sequence": 2,
            "command_type": "MANUAL",
            "duration_ms": 15000,
        }))
        assert simulator.gate_state == "OPEN"
        assert simulator.gate_mode == "MANUAL_LATCHED_OPEN"
        assert simulator.auto_close_task is None
        assert simulator.lcd_line1 == "MANUAL GATE OPEN"
        assert simulator.lcd_line2 == "WAITING TO CLOSE"

        await asyncio.sleep(0.05)
        await simulator.handle_message(json.dumps({
            "type": "GATE_CLOSE",
            "command_id": "automated-close",
            "command_sequence": 3,
            "command_type": "AUTOMATED",
        }))
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "automated-open",
            "command_sequence": 4,
            "command_type": "AUTOMATED",
            "duration_ms": 1000,
        }))
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "repeated-manual-open",
            "command_sequence": 5,
            "command_type": "MANUAL",
            "duration_ms": 1000,
        }))
        await simulator.send_heartbeat()

        assert simulator.gate_state == "OPEN"
        assert simulator.gate_mode == "MANUAL_LATCHED_OPEN"
        assert simulator.auto_close_task is None
        assert simulator.lcd_line2 == "WAITING TO CLOSE"
        heartbeat = next(
            packet for packet in simulator.sent_packets
            if packet.get("type") == "HEARTBEAT"
        )
        assert heartbeat["state"] == "OPEN"
        assert heartbeat["gate_mode"] == "MANUAL_LATCHED_OPEN"

        await simulator.handle_message(json.dumps({
            "type": "GATE_CLOSE",
            "command_id": "manual-close",
            "command_sequence": 6,
            "command_type": "MANUAL",
        }))
        assert simulator.gate_state == "CLOSED"
        assert simulator.gate_mode == "AUTOMATED"
        assert simulator.lcd_line1 == "GATE CLOSED"
        assert simulator.lcd_line2 == "SYSTEM READY"
        assert any(
            packet.get("command_id") == "automated-close"
            and packet.get("status") == "REJECTED"
            for packet in simulator.sent_packets
        )
        assert any(
            packet.get("command_id") == "automated-open"
            and packet.get("status") == "REJECTED"
            for packet in simulator.sent_packets
        )

    asyncio.run(exercise_manual_latch())


def test_simulator_automated_open_still_auto_closes():
    from scripts.mock_esp32 import MockEsp32Controller

    async def exercise_automated_timer():
        simulator = MockEsp32Controller(
            "ws://127.0.0.1:8001/api/v1/ws/iot/gate",
            "test-device",
            "test-only-device-token",
        )

        async def capture_json(_payload):
            return None

        simulator.send_json = capture_json
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "automated-open",
            "command_sequence": 1,
            "command_type": "AUTOMATED",
            "duration_ms": 40,
        }))
        assert simulator.gate_mode == "AUTOMATED"
        assert simulator.auto_close_task is not None
        await asyncio.sleep(0.08)
        assert simulator.gate_state == "CLOSED"
        assert simulator.gate_mode == "AUTOMATED"

    asyncio.run(exercise_automated_timer())


def test_service_authentication_accepts_controlled_test_secret():
    response = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": "test-only-service-secret-1234567890"},
        json={"event_id": str(uuid.uuid4()), "status": "MANUAL_REVIEW"},
    )
    assert response.status_code == 200


def test_service_authentication_rejects_controlled_invalid_secret():
    response = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": "invalid-test-secret"},
        json={"event_id": str(uuid.uuid4()), "status": "MANUAL_REVIEW"},
    )
    assert response.status_code == 403


def test_device_authentication_accepts_only_controlled_identity_and_token():
    assert device_manager.authenticate_device("test-device", "test-only-device-token")
    assert not device_manager.authenticate_device("wrong-device", "test-only-device-token")
    assert not device_manager.authenticate_device("test-device", "invalid-test-device-token")


def test_gate_status_auth_missing_secret():
    response = client.post(
        "/api/v1/gate/status",
        json={"event_id": str(uuid.uuid4()), "status": "GATE_OPEN"},
    )
    assert response.status_code == 403


def test_gate_status_auth_invalid_secret():
    response = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": "invalid_wrong_secret"},
        json={"event_id": str(uuid.uuid4()), "status": "GATE_OPEN"},
    )
    assert response.status_code == 403


def test_gate_status_valid_secret_device_offline():
    """When device is offline, command returns success=False without crashing."""
    event_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": settings.iot_service_secret},
        json={"event_id": event_id, "status": "GATE_OPEN"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["event_id"] == event_id
    assert data["requested_status"] == "GATE_OPEN"
    # Hardware command fails because device is offline
    assert data["command_result"]["success"] is False
    assert data["command_result"]["error"] == "DEVICE_OFFLINE"


def test_gate_status_idempotency():
    """Duplicate event_id is acknowledged with DUPLICATE status."""
    event_id = f"idem-{uuid.uuid4()}"

    res1 = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": settings.iot_service_secret},
        json={"event_id": event_id, "status": "MANUAL_REVIEW"},
    )
    assert res1.status_code == 200

    # Second call with identical event_id
    res2 = client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": settings.iot_service_secret},
        json={"event_id": event_id, "status": "MANUAL_REVIEW"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["accepted"] is True
    assert data2["command_result"]["status"] == "DUPLICATE"


def test_manual_open_requires_operator_role():
    # Invalid service credential is rejected even with a valid claimed role.
    res_invalid_secret = client.post(
        "/api/v1/gate/manual-open",
        headers={
            "X-Service-Secret": "invalid-test-secret",
            "X-Operator-Role": "SECURITY",
            "X-Operator-Id": "guard-42",
        },
        json={"reason": "Testing invalid service secret"},
    )
    assert res_invalid_secret.status_code == 403

    # Missing role
    res = client.post(
        "/api/v1/gate/manual-open",
        headers={"X-Service-Secret": settings.iot_service_secret},
        json={"reason": "Testing manual open"},
    )
    assert res.status_code == 403

    # Invalid role (e.g. VISITOR or RESIDENT)
    res_resident = client.post(
        "/api/v1/gate/manual-open",
        headers={
            "X-Service-Secret": settings.iot_service_secret,
            "X-Operator-Role": "RESIDENT",
        },
        json={"reason": "Testing unauthorized role"},
    )
    assert res_resident.status_code == 403

    # Valid role SECURITY
    res_security = client.post(
        "/api/v1/gate/manual-open",
        headers={
            "X-Service-Secret": settings.iot_service_secret,
            "X-Operator-Role": "SECURITY",
            "X-Operator-Id": "guard-42",
        },
        json={"reason": "Emergency vehicle entry"},
    )
    assert res_security.status_code == 200
    data = res_security.json()
    assert "accepted" in data


def test_manual_close_requires_operator_role():
    # Valid role ADMIN
    res = client.post(
        "/api/v1/gate/manual-close",
        headers={
            "X-Service-Secret": settings.iot_service_secret,
            "X-Operator-Role": "ADMIN",
            "X-Operator-Id": "admin-1",
        },
        json={"reason": "Manual operator closure"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "accepted" in data


def test_manual_routes_mark_commands_and_use_latching_lcd_messages(monkeypatch):
    sent_commands = []

    async def fake_open(**kwargs):
        sent_commands.append(("open", kwargs))
        return {"success": True, "delivered": True, "controller_acknowledged": True}

    async def fake_close(**kwargs):
        sent_commands.append(("close", kwargs))
        return {"success": True, "delivered": True, "controller_acknowledged": True}

    monkeypatch.setattr(device_manager, "send_gate_open", fake_open)
    monkeypatch.setattr(device_manager, "send_gate_close", fake_close)
    headers = {
        "X-Service-Secret": settings.iot_service_secret,
        "X-Operator-Role": "SECURITY",
        "X-Operator-Id": "guard-test",
    }

    open_response = client.post("/api/v1/gate/manual-open", headers=headers, json={})
    close_response = client.post("/api/v1/gate/manual-close", headers=headers, json={})

    assert open_response.status_code == 200
    assert close_response.status_code == 200
    assert sent_commands[0][1]["command_type"] == "MANUAL"
    assert sent_commands[0][1]["line1"] == "MANUAL GATE OPEN"
    assert sent_commands[0][1]["line2"] == "WAITING TO CLOSE"
    assert sent_commands[1][1]["command_type"] == "MANUAL"
    assert sent_commands[1][1]["line1"] == "GATE CLOSED"
    assert sent_commands[1][1]["line2"] == "SYSTEM READY"


def test_automated_reset_close_is_not_manual_latch_release(monkeypatch):
    captured = {}

    async def fake_close(**kwargs):
        captured.update(kwargs)
        return {
            "success": False,
            "delivered": True,
            "controller_acknowledged": False,
            "status": "REJECTED",
        }

    monkeypatch.setattr(device_manager, "send_gate_close", fake_close)
    response = client.post(
        "/api/v1/gate/manual-close",
        headers={
            "X-Service-Secret": settings.iot_service_secret,
            "X-Operator-Role": "SECURITY",
            "X-Operator-Id": "guard-test",
        },
        json={"reason": "Operator reset", "command_type": "AUTOMATED"},
    )

    assert response.status_code == 200
    assert captured["command_type"] == "AUTOMATED"


def test_device_events_buffer():
    # Trigger an action to record an event
    client.post(
        "/api/v1/gate/status",
        headers={"X-Service-Secret": settings.iot_service_secret},
        json={"event_id": str(uuid.uuid4()), "status": "MANUAL_REVIEW"},
    )

    events_res = client.get(
        "/api/v1/device/events",
        headers={"X-Service-Secret": "test-only-service-secret-1234567890"},
    )
    assert events_res.status_code == 200
    events = events_res.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert any(e["event_type"] == "STATUS_RECEIVED" for e in events)


def test_esp32_websocket_heartbeat():
    """Simulate ESP32 connecting and sending a HEARTBEAT packet."""
    ws_url = f"/api/v1/ws/iot/gate?device_id={settings.iot_device_id}&token={settings.iot_device_key}"

    with client.websocket_connect(ws_url) as ws:
        # Send heartbeat
        hb = {
            "type": "HEARTBEAT",
            "device_id": settings.iot_device_id,
            "gate_state": "CLOSED",
            "uptime_seconds": 150,
            "free_heap": 185000,
            "wifi_rssi": -60,
        }
        ws.send_text(json.dumps(hb))

        # Give test client portal a moment to process the frame
        import time
        for _ in range(20):
            if device_manager._uptime_seconds == 150:
                break
            time.sleep(0.02)

        # Check device manager status updated
        status = device_manager.get_status()
        assert status["is_connected"] is True
        assert status["device_id"] == settings.iot_device_id
        assert status["uptime_seconds"] == 150
        assert status["wifi_rssi"] == -60
        assert status["reported_gate_state"] == "CLOSED"


def test_heartbeat_and_state_reports_expose_manual_latch_mode():
    async def report_manual_state():
        await device_manager._process_incoming(json.dumps({
            "type": "HEARTBEAT",
            "device_id": "test-device",
            "state": "OPEN",
            "gate_mode": "MANUAL_LATCHED_OPEN",
        }))
        status = device_manager.get_status()
        assert status["reported_gate_state"] == "OPEN"
        assert status["reported_gate_mode"] == "MANUAL_LATCHED_OPEN"

        await device_manager._process_incoming(json.dumps({
            "type": "GATE_STATE",
            "device_id": "test-device",
            "state": "CLOSED",
            "gate_mode": "AUTOMATED",
        }))
        status = device_manager.get_status()
        assert status["reported_gate_state"] == "CLOSED"
        assert status["reported_gate_mode"] == "AUTOMATED"

    asyncio.run(report_manual_state())


def test_accepted_ack_is_receipt_only_until_final_execution_ack():
    async def exercise_acknowledgements():
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        device_manager._pending_acks["test-command"] = future
        await device_manager._process_incoming(json.dumps({
            "type": "COMMAND_ACK",
            "command_id": "test-command",
            "status": "ACCEPTED",
        }))
        assert not future.done()
        await device_manager._process_incoming(json.dumps({
            "type": "COMMAND_ACK",
            "command_id": "test-command",
            "status": "EXECUTED",
            "detail": "Servo target set; not sensor-verified",
        }))
        assert future.result()["status"] == "EXECUTED"

    asyncio.run(exercise_acknowledgements())


def test_older_connection_cleanup_cannot_clear_replacement_connection():
    old_connection = object()
    new_connection = object()
    device_manager._device_ws = new_connection
    device_manager._connected = True
    device_manager._device_id = "test-device"

    device_manager._cleanup_device(old_connection)

    assert device_manager._device_ws is new_connection
    assert device_manager._connected is True
    assert device_manager._device_id == "test-device"


def test_manual_close_order_rejects_delayed_older_open():
    open_sequence = device_manager._next_command_sequence(1_000)
    close_sequence = device_manager._next_command_sequence(2_000)
    stale_open_sequence = device_manager._next_command_sequence(1_500)

    assert close_sequence > open_sequence
    assert stale_open_sequence is None
    assert device_manager._latest_command_sequence == close_sequence


def test_simulator_manual_close_cannot_be_undone_by_stale_open_or_timer():
    from scripts.mock_esp32 import MockEsp32Controller

    async def exercise_commands():
        simulator = MockEsp32Controller(
            "ws://127.0.0.1:8001/api/v1/ws/iot/gate",
            "test-device",
            "test-only-device-token",
        )
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "open-old",
            "command_sequence": 1,
            "duration_ms": 80,
        }))
        await asyncio.sleep(0.01)
        await simulator.handle_message(json.dumps({
            "type": "GATE_CLOSE",
            "command_id": "close-new",
            "command_sequence": 2,
        }))
        await simulator.handle_message(json.dumps({
            "type": "GATE_OPEN",
            "command_id": "open-delayed",
            "command_sequence": 1,
            "duration_ms": 80,
        }))
        await asyncio.sleep(0.1)
        assert simulator.gate_state == "CLOSED"
        if simulator.auto_close_task:
            simulator.auto_close_task.cancel()

    asyncio.run(exercise_commands())
