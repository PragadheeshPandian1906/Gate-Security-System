"""
SmartGuard AI — Phase 5 Visitor Management Unit Tests

Tests:
  - Cryptographic token generation and SHA-256 hashing (raw token is never persisted)
  - QR PNG image generation and dual-storage integration
  - Visitor pass creation and validity window validation
  - QR credential scan:
      - Valid ENTRY scan creates PENDING VisitorApproval; simulated gate remains CLOSED
      - Valid EXIT scan marks pass COMPLETED and actuates gate
      - Safe exit: an already inside visitor CAN exit even if their entry window has passed
      - Revoked pass scan is DENIED
      - Invalid token scan is DENIED and triggers alert
  - Security officer approval:
      - Explicit approval marks pass ACTIVE_INSIDE, creates AccessAttempt, actuates gate
      - Denial marks pass DENIED, records AccessAttempt, keeps gate closed
  - Visitor API endpoints
"""
import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_active_account, require_security
from app.db.session import get_db
from app.main import app
from app.models.account import SecurityAccount
from app.models.access import AccessAttempt
from app.models.people import CampusPerson
from app.models.visitors import VisitorApproval, VisitorPass
from app.services import gate_service, visitor_service


# ---------------------------------------------------------------------------
# Unit Tests: Token Generation & Security
# ---------------------------------------------------------------------------
def test_generate_qr_credential_security():
    """Verify raw token has high entropy and token_hash is its exact SHA-256 digest."""
    raw_token, token_hash = visitor_service.generate_qr_credential()

    # Raw token should be non-empty and high-entropy urlsafe string
    assert len(raw_token) >= 32
    assert len(token_hash) == 64

    # Hash verification
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    assert token_hash == expected_hash

    # Hashing helper handles optional SGVP: prefix
    assert visitor_service.hash_token(raw_token) == token_hash
    assert visitor_service.hash_token(f"SGVP:{raw_token}") == token_hash


def test_render_qr_image_bytes():
    """Verify QR code PNG bytes are successfully rendered."""
    payload = "SGVP:test_token_12345"
    png_bytes = visitor_service.render_qr_image_bytes(payload)

    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 100
    # PNG signature check: \x89PNG\r\n\x1a\n
    assert png_bytes[:4] == b"\x89PNG"


def test_pass_validity_window_validation():
    """Creating a pass where valid_until <= valid_from must raise ValueError."""
    mock_db = MagicMock()
    now = datetime.now(timezone.utc)

    # valid_until earlier than valid_from
    with pytest.raises(ValueError, match="valid_until timestamp must be after valid_from"):
        visitor_service.create_visitor_pass(
            mock_db,
            valid_from=now,
            valid_until=now - timedelta(hours=1),
            full_name="John Visitor",
            email="john@example.com",
            send_email=False,
        )


# ---------------------------------------------------------------------------
# Unit Tests: Pass Creation & Raw Token Separation
# ---------------------------------------------------------------------------
@patch("app.services.storage_service.save_file")
@patch("app.services.visitor_service.dispatch_visitor_pass_email")
def test_create_visitor_pass_persists_hash_not_raw(mock_email, mock_storage):
    """Verify VisitorPass model stores token_hash, and raw_token is only returned."""
    mock_storage.return_value = MagicMock(local_path="/tmp/qr.png", storage_path="visitor-qr/qr.png")
    mock_email.return_value = "SENT"

    mock_db = MagicMock()
    # Mock visitor person
    mock_visitor = CampusPerson(
        id=uuid.uuid4(),
        full_name="Alice Smith",
        person_type="visitor",
        email="alice@example.com",
        status="active",
    )
    mock_db.get.return_value = mock_visitor

    now = datetime.now(timezone.utc)
    vpass, raw_token, qr_b64 = visitor_service.create_visitor_pass(
        mock_db,
        valid_from=now,
        valid_until=now + timedelta(hours=8),
        visitor_id=mock_visitor.id,
        purpose="Vendor Meeting",
        send_email=True,
    )

    # Verify pass attributes
    assert vpass.status == "ISSUED"
    assert vpass.purpose == "Vendor Meeting"
    assert vpass.token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    # Ensure raw_token is not on the VisitorPass model itself
    assert not hasattr(vpass, "raw_token")
    assert len(qr_b64) > 50

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Unit Tests: Scanning & Lifecycle State Machine
# ---------------------------------------------------------------------------
def test_invalid_qr_scan_rejected():
    """An unknown QR token must be denied and keep gate closed."""
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    result = visitor_service.scan_and_verify_pass(
        mock_db,
        qr_credential="SGVP:non_existent_token",
        direction="ENTRY",
    )

    assert result["status"] == "DENIED"
    assert "Invalid QR code" in result["message"]
    assert result["gate_state"] == "CLOSED"


@patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "detail": "Open"})
def test_valid_entry_scan_creates_pending_approval_and_keeps_gate_closed(mock_sched):
    """A valid QR scan for ENTRY must create a PENDING approval and keep gate CLOSED."""
    mock_db = MagicMock()
    now = datetime.now(timezone.utc)

    # Mock valid pass
    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-TEST1",
        visitor_id=uuid.uuid4(),
        token_hash=hashlib.sha256(b"secret123").hexdigest(),
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=4),
        status="ISSUED",
    )
    mock_visitor = CampusPerson(
        id=vpass.visitor_id,
        full_name="Bob Visitor",
        person_type="visitor",
    )

    # DB execute mock for pass lookup & approval lookup
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [vpass, None]
    mock_db.get.side_effect = lambda model, id_: mock_visitor if model == CampusPerson else None

    # Before scan, ensure gate starts CLOSED
    gate_service.force_close()

    result = visitor_service.scan_and_verify_pass(
        mock_db,
        qr_credential="SGVP:secret123",
        direction="ENTRY",
        scanned_by=uuid.uuid4(),
    )

    assert result["status"] == "PENDING_APPROVAL"
    assert result["gate_state"] == "CLOSED"
    assert result["pass_number"] == "VP-20261018-TEST1"
    assert vpass.status == "PENDING_APPROVAL"

    # Gate MUST remain closed
    status_snap = gate_service.get_status()
    assert status_snap["state"] == "CLOSED"


@patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "detail": "Open"})
def test_security_officer_approval_workflow(mock_sched):
    """Security officer explicit approval sets pass ACTIVE_INSIDE and opens gate."""
    mock_db = MagicMock()
    now = datetime.now(timezone.utc)
    officer_id = uuid.uuid4()

    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-APP1",
        visitor_id=uuid.uuid4(),
        token_hash="dummyhash",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=4),
        status="PENDING_APPROVAL",
    )
    approval = VisitorApproval(
        id=uuid.uuid4(),
        pass_id=vpass.id,
        visitor_id=vpass.visitor_id,
        status="PENDING",
        direction="ENTRY",
    )
    officer = SecurityAccount(
        id=officer_id,
        username="officer_dan",
        role="SECURITY",
        status="active",
    )

    mock_db.execute.return_value.scalar_one_or_none.side_effect = [approval, vpass]
    mock_db.get.side_effect = lambda model, id_: officer if model == SecurityAccount else None

    # Gate starts CLOSED
    gate_service.force_close()

    updated_pass, attempt = visitor_service.approve_visitor_entry(
        mock_db,
        approval_id=approval.id,
        officer_id=officer_id,
        notes="Identity verified with driver's license",
    )

    assert approval.status == "APPROVED"
    assert updated_pass.status == "ACTIVE_INSIDE"
    assert updated_pass.check_in_at is not None
    assert attempt.decision == "ALLOW"
    assert attempt.gate_result == "OPEN"
    assert attempt.visitor_pass_id == vpass.id

    # Gate barrier must now be OPEN
    status_snap = gate_service.get_status()
    assert status_snap["state"] == "OPEN"


@patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "detail": "Open"})
def test_security_officer_denial_workflow(mock_sched):
    """Security officer denial sets pass DENIED and keeps gate CLOSED."""
    mock_db = MagicMock()
    officer_id = uuid.uuid4()

    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-DENY1",
        visitor_id=uuid.uuid4(),
        token_hash="dummyhash",
        status="PENDING_APPROVAL",
    )
    approval = VisitorApproval(
        id=uuid.uuid4(),
        pass_id=vpass.id,
        visitor_id=vpass.visitor_id,
        status="PENDING",
        direction="ENTRY",
    )

    mock_db.execute.return_value.scalar_one_or_none.side_effect = [approval, vpass]
    mock_db.get.return_value = None

    gate_service.force_close()

    updated_pass, attempt = visitor_service.deny_visitor_entry(
        mock_db,
        approval_id=approval.id,
        officer_id=officer_id,
        denial_reason="Suspicious baggage",
    )

    assert approval.status == "DENIED"
    assert updated_pass.status == "DENIED"
    assert attempt.decision == "DENY"
    assert attempt.gate_result == "CLOSED"

    status_snap = gate_service.get_status()
    assert status_snap["state"] == "CLOSED"


@patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "detail": "Open"})
def test_visitor_exit_marks_pass_completed_and_opens_gate(mock_sched):
    """An active inside visitor scanning EXIT completes their pass and opens gate."""
    mock_db = MagicMock()
    now = datetime.now(timezone.utc)

    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-EXIT1",
        visitor_id=uuid.uuid4(),
        token_hash=hashlib.sha256(b"exit_token").hexdigest(),
        valid_from=now - timedelta(hours=3),
        valid_until=now + timedelta(hours=1),
        status="ACTIVE_INSIDE",
    )
    mock_visitor = CampusPerson(
        id=vpass.visitor_id,
        full_name="Carol White",
        person_type="visitor",
    )

    mock_db.execute.return_value.scalar_one_or_none.return_value = vpass
    mock_db.get.side_effect = lambda model, id_: mock_visitor if model == CampusPerson else None

    gate_service.force_close()

    result = visitor_service.scan_and_verify_pass(
        mock_db,
        qr_credential="SGVP:exit_token",
        direction="EXIT",
        scanned_by=uuid.uuid4(),
    )

    assert result["status"] == "COMPLETED"
    assert result["gate_state"] == "OPEN"
    assert vpass.status == "COMPLETED"
    assert vpass.check_out_at is not None

    status_snap = gate_service.get_status()
    assert status_snap["state"] == "OPEN"


@patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "detail": "Open"})
def test_visitor_can_exit_even_if_entry_window_expired(mock_sched):
    """
    CRITICAL EDGE CASE:
    A visitor entered when valid, but their valid_until has passed while inside.
    They MUST be permitted to safely exit!
    """
    mock_db = MagicMock()
    now = datetime.now(timezone.utc)

    # valid_until is 1 hour in the past!
    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-OVERDUE",
        visitor_id=uuid.uuid4(),
        token_hash=hashlib.sha256(b"overdue_token").hexdigest(),
        valid_from=now - timedelta(hours=5),
        valid_until=now - timedelta(hours=1),
        status="ACTIVE_INSIDE",
    )
    mock_visitor = CampusPerson(
        id=vpass.visitor_id,
        full_name="Dave Overdue",
        person_type="visitor",
    )

    mock_db.execute.return_value.scalar_one_or_none.return_value = vpass
    mock_db.get.side_effect = lambda model, id_: mock_visitor if model == CampusPerson else None

    gate_service.force_close()

    result = visitor_service.scan_and_verify_pass(
        mock_db,
        qr_credential="SGVP:overdue_token",
        direction="EXIT",
        scanned_by=uuid.uuid4(),
    )

    # Even though valid_until is expired, EXIT must succeed
    assert result["status"] == "COMPLETED"
    assert result["gate_state"] == "OPEN"
    assert vpass.status == "COMPLETED"


def test_revoked_pass_cannot_enter():
    """A revoked pass presented for ENTRY must be rejected."""
    mock_db = MagicMock()
    vpass = VisitorPass(
        id=uuid.uuid4(),
        pass_number="VP-20261018-REV1",
        visitor_id=uuid.uuid4(),
        token_hash=hashlib.sha256(b"revoked_token").hexdigest(),
        status="REVOKED",
        revocation_reason="Security policy violation",
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = vpass
    mock_db.get.return_value = None

    result = visitor_service.scan_and_verify_pass(
        mock_db,
        qr_credential="SGVP:revoked_token",
        direction="ENTRY",
    )

    assert result["status"] == "DENIED"
    assert "revoked" in result["message"]
    assert result["gate_state"] == "CLOSED"


# ---------------------------------------------------------------------------
# API Route Integration Tests (with mock dependency overrides)
# ---------------------------------------------------------------------------
@pytest.fixture
def test_client_with_auth(security_account):
    """FastAPI TestClient with security role override."""
    def override_get_db():
        mock = MagicMock()
        try:
            yield mock
        finally:
            pass

    def override_security():
        return security_account

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_security] = override_security
    app.dependency_overrides[get_active_account] = override_security

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


def test_get_metrics_endpoint(test_client_with_auth):
    """Test GET /api/visitors/passes/metrics returns expected structure."""
    with patch("app.services.visitor_service.get_visitor_metrics") as mock_m:
        mock_m.return_value = {
            "active_passes": 5,
            "pending_approvals": 2,
            "visitors_inside": 3,
            "completed_today": 8,
            "revoked_or_expired": 1,
        }
        res = test_client_with_auth.get("/api/visitors/passes/metrics")
        assert res.status_code == 200
        data = res.json()
        assert data["active_passes"] == 5
        assert data["pending_approvals"] == 2
        assert data["visitors_inside"] == 3


def test_scan_endpoint_entry(test_client_with_auth):
    """Test POST /api/visitors/scan calls scan_and_verify_pass."""
    with patch("app.services.visitor_service.scan_and_verify_pass") as mock_scan:
        mock_scan.return_value = {
            "status": "PENDING_APPROVAL",
            "message": "Pass verified. Awaiting officer approval.",
            "pass_number": "VP-20261018-SCAN",
            "direction": "ENTRY",
            "gate_state": "CLOSED",
        }
        res = test_client_with_auth.post(
            "/api/visitors/scan",
            json={"qr_credential": "SGVP:sampletoken123", "direction": "ENTRY"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "PENDING_APPROVAL"
        assert data["gate_state"] == "CLOSED"


def test_dispatch_visitor_pass_email_handles_email_service_dict():
    """Verify dispatch_visitor_pass_email properly handles dict response from email_service."""
    mock_db = MagicMock()
    mock_pass = MagicMock()
    mock_pass.id = uuid.uuid4()
    mock_pass.pass_number = "VP-20261019-TEST"
    mock_pass.purpose = "Vendor Delivery"
    mock_pass.vehicle_plate = "KA01AB1234"
    mock_pass.valid_from = datetime.now(timezone.utc)
    mock_pass.valid_until = datetime.now(timezone.utc) + timedelta(hours=4)

    mock_visitor = MagicMock()
    mock_visitor.email = "visitor@example.com"
    mock_visitor.full_name = "Jane Visitor"

    with patch("app.services.email_service.send_email") as mock_send, \
         patch("app.services.email_service.is_email_enabled", return_value=True):
        mock_send.return_value = {
            "success": True,
            "provider_message_id": "<brevo-msg-123>",
            "error": None,
        }
        res = visitor_service.dispatch_visitor_pass_email(
            mock_db,
            mock_pass,
            mock_visitor,
            "fakebase64qrdata",
        )
        assert res == "SENT"
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["to_address"] == "visitor@example.com"
        assert mock_send.call_args.kwargs["to_name"] == "Jane Visitor"


def test_issue_pass_endpoint(test_client_with_auth):
    """Test POST /api/visitors/passes creates pass and returns 201 with QR base64."""
    mock_pass = MagicMock()
    mock_pass.id = uuid.uuid4()
    mock_pass.pass_number = "VP-20261019-API"
    mock_pass.visitor_id = uuid.uuid4()
    mock_pass.host_person_id = None
    mock_pass.vehicle_id = None
    mock_pass.vehicle_plate = None
    mock_pass.purpose = "Meeting"
    mock_pass.organization = "Acme"
    mock_pass.id_type = "national_id"
    mock_pass.id_number = "ID-999"
    mock_pass.valid_from = datetime.now(timezone.utc)
    mock_pass.valid_until = datetime.now(timezone.utc) + timedelta(hours=8)
    mock_pass.status = "ISSUED"
    mock_pass.qr_code_path = "/tmp/qr.png"
    mock_pass.issued_at = datetime.now(timezone.utc)
    mock_pass.issued_by = None
    mock_pass.check_in_at = None
    mock_pass.check_out_at = None
    mock_pass.revoked_at = None
    mock_pass.revocation_reason = None

    now = datetime.now(timezone.utc)
    with patch("app.services.visitor_service.create_visitor_pass") as mock_create, \
         patch("app.api.routes.visitors._pass_to_response") as mock_conv:
        mock_create.return_value = (mock_pass, "secrettoken", "fake_qr_b64_string")
        from app.schemas.visitors import VisitorPassResponse
        mock_conv.return_value = VisitorPassResponse(
            id=str(mock_pass.id),
            pass_number=mock_pass.pass_number,
            visitor_id=str(mock_pass.visitor_id),
            visitor_name="John Doe",
            purpose="Meeting",
            valid_from=now,
            valid_until=now + timedelta(hours=8),
            status="ISSUED",
            qr_code_base64="fake_qr_b64_string",
            qr_image_base64="fake_qr_b64_string",
            issued_at=now,
        )

        res = test_client_with_auth.post(
            "/api/visitors/passes",
            json={
                "full_name": "John Doe",
                "phone": "+919876543210",
                "email": "johndoe@example.com",
                "purpose": "Meeting",
                "valid_from": now.isoformat(),
                "valid_until": (now + timedelta(hours=8)).isoformat(),
                "send_email": True,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["pass_number"] == "VP-20261019-API"
        assert data["qr_code_base64"] == "fake_qr_b64_string"

