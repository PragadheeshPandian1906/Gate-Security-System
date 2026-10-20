"""
SmartGuard AI — Phase 3 Unit Tests

Comprehensive unit tests for Phase 3:
- Gate state machine simulation (CLOSED -> OPEN -> MANUAL_REVIEW)
- Schedule evaluation (Operating hours, closed days, unavailable fail-closed)
- Watchlist evaluation (Severity handling and plate normalization)
- Decision Engine precedence rules (Fail-closed)
- Phase 3 API endpoints (gate status & reset, pending reviews)
"""
import uuid
from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.main import app
from app.db.session import get_db
from app.api.dependencies import require_security, require_admin, get_active_account
from app.models.account import SecurityAccount
from app.services.gate_service import (
    get_status,
    apply_decision,
    force_close,
)
from app.services.schedule_service import (
    evaluate_schedule,
)
from app.services.watchlist_service import (
    check_watchlist,
)
from app.services.access_decision_service import evaluate_access_attempt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_account():
    acc = MagicMock(spec=SecurityAccount)
    acc.id = uuid.uuid4()
    acc.username = "officer1"
    acc.role = "security"
    acc.is_active = True
    return acc


@pytest.fixture
def mock_admin_account():
    acc = MagicMock(spec=SecurityAccount)
    acc.id = uuid.uuid4()
    acc.username = "admin1"
    acc.role = "admin"
    acc.is_active = True
    return acc


# ---------------------------------------------------------------------------
# 1. Gate State Machine
# ---------------------------------------------------------------------------

class TestGateService:
    def test_gate_initial_or_reset(self):
        status = force_close("test")
        assert status["state"] == "CLOSED"
        assert "no physical barrier" in status["simulation_note"]

    def test_gate_allow_opens(self):
        attempt_id = str(uuid.uuid4())
        state = apply_decision("ALLOW", "ENTRY", attempt_id)
        assert state == "OPEN"
        status = get_status()
        assert status["state"] == "OPEN"
        assert status["last_decision"] == "ALLOW"
        assert status["last_attempt_id"] == attempt_id

    def test_gate_deny_closes(self):
        attempt_id = str(uuid.uuid4())
        state = apply_decision("DENY", "ENTRY", attempt_id)
        assert state == "CLOSED"
        status = get_status()
        assert status["state"] == "CLOSED"
        assert status["last_decision"] == "DENY"

    def test_gate_manual_review_holds(self):
        attempt_id = str(uuid.uuid4())
        state = apply_decision("MANUAL_REVIEW", "EXIT", attempt_id)
        assert state == "MANUAL_REVIEW"
        status = get_status()
        assert status["state"] == "MANUAL_REVIEW"
        assert status["last_direction"] == "EXIT"


# ---------------------------------------------------------------------------
# 2. Schedule Service
# ---------------------------------------------------------------------------

class TestScheduleService:
    def test_evaluate_schedule_empty_db_fails_closed(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = evaluate_schedule(mock_db)
        assert result["ok"] is False
        assert result["reason_code"] == "SCHEDULE_UNAVAILABLE"

    def test_evaluate_schedule_closed_day(self):
        mock_db = MagicMock()
        mock_entry = MagicMock()
        weekday_name = datetime.now(timezone.utc).strftime("%A").lower()
        mock_entry.weekday = weekday_name
        mock_entry.is_open = False
        mock_entry.campus_timezone = "Asia/Kolkata"
        mock_entry.open_time = None
        mock_entry.close_time = None

        with patch("app.services.schedule_service._load_schedule", return_value=[mock_entry]):
            result = evaluate_schedule(mock_db)
            assert result["ok"] is False
            assert result["reason_code"] == "OUTSIDE_SCHEDULE"

    def test_evaluate_schedule_open_hours(self):
        mock_db = MagicMock()
        mock_entry = MagicMock()
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        now_local = datetime.now(tz)
        weekday_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][now_local.weekday()]

        mock_entry.weekday = weekday_name
        mock_entry.is_open = True
        mock_entry.campus_timezone = "Asia/Kolkata"
        mock_entry.open_time = "00:00"
        mock_entry.close_time = "23:59"

        with patch("app.services.schedule_service._load_schedule", return_value=[mock_entry]):
            result = evaluate_schedule(mock_db, at_time=now_local)
            assert result["ok"] is True
            assert result["reason_code"] == "SCHEDULE_OK"


# ---------------------------------------------------------------------------
# 3. Watchlist Service
# ---------------------------------------------------------------------------

class TestWatchlistService:
    def test_watchlist_no_hit(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        res = check_watchlist(mock_db, plate_normalized="KA01MJ9999", vehicle_id=None)
        assert res["hit"] is False
        assert res["severity"] is None

    def test_watchlist_high_severity_hit(self):
        mock_db = MagicMock()
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.plate_normalized = "KA01MJ9999"
        entry.vehicle_id = None
        entry.severity = "high"
        entry.reason = "Stolen vehicle report"
        entry.is_active = True
        entry.expires_at = None

        mock_db.execute.return_value.scalars.return_value.all.return_value = [entry]
        res = check_watchlist(mock_db, plate_normalized="KA01MJ9999", vehicle_id=None)
        assert res["hit"] is True
        assert res["severity"] == "high"
        assert res["reason_code"] == "WATCHLIST_BLOCK"


# ---------------------------------------------------------------------------
# 4. Access Decision Engine (Precedence Order)
# ---------------------------------------------------------------------------

class TestAccessDecisionEngine:
    def test_decision_no_face_denies(self):
        mock_db = MagicMock()
        face_ver = {
            "id": str(uuid.uuid4()),
            "result": "no_face",
            "confidence": None,
            "faces_detected": 0,
        }
        with patch("app.services.access_decision_service._get_face_verification", return_value=face_ver):
            with patch("app.services.access_decision_service._persist_attempt", return_value=str(uuid.uuid4())):
                resp = evaluate_access_attempt(
                    db=mock_db,
                    direction="ENTRY",
                    face_verification_id=face_ver["id"],
                    alpr_verification_id=None,
                    initiated_by=str(uuid.uuid4()),
                )
                assert resp["decision"] == "DENY"
                assert "FACE_NOT_DETECTED" in resp["reason_codes"]

    def test_decision_watchlist_high_blocks(self):
        mock_db = MagicMock()
        person_id = str(uuid.uuid4())
        vehicle_id = str(uuid.uuid4())

        face_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "confidence": 0.85,
            "matched_person_id": person_id,
            "faces_detected": 1,
        }
        alpr_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "detected_plate": "KA01MJ9999",
            "detected_plate_normalized": "KA01MJ9999",
            "matched_vehicle_id": vehicle_id,
        }
        mock_person = {"id": person_id, "full_name": "John Doe", "status": "active", "person_type": "staff"}
        mock_vehicle = {"id": vehicle_id, "plate_number": "KA01MJ9999", "plate_normalized": "KA01MJ9999", "status": "active", "owner_person_id": person_id, "owner_name": "John Doe"}

        with patch("app.services.access_decision_service._get_face_verification", return_value=face_ver):
            with patch("app.services.access_decision_service._get_alpr_verification", return_value=alpr_ver):
                with patch("app.services.access_decision_service._get_person", return_value=mock_person):
                    with patch("app.services.access_decision_service._get_vehicle", return_value=mock_vehicle):
                        with patch("app.services.watchlist_service.check_watchlist", return_value={
                            "hit": True,
                            "severity": "high",
                            "reason_code": "WATCHLIST_BLOCK",
                            "reason_text": "Watchlist high severity match",
                            "entry_id": str(uuid.uuid4()),
                            "entry_reason": "High risk",
                        }):
                            with patch("app.services.access_decision_service._persist_attempt", return_value=str(uuid.uuid4())):
                                resp = evaluate_access_attempt(
                                    db=mock_db,
                                    direction="ENTRY",
                                    face_verification_id=face_ver["id"],
                                    alpr_verification_id=alpr_ver["id"],
                                    initiated_by=str(uuid.uuid4()),
                                )
                                assert resp["decision"] == "DENY"
                                assert "WATCHLIST_BLOCK" in resp["reason_codes"]

    def test_decision_owner_mismatch_triggers_manual_review(self):
        mock_db = MagicMock()
        person_id = str(uuid.uuid4())
        other_person_id = str(uuid.uuid4())
        vehicle_id = str(uuid.uuid4())

        face_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "confidence": 0.88,
            "matched_person_id": person_id,
            "faces_detected": 1,
        }
        alpr_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "detected_plate": "TN09BK5678",
            "detected_plate_normalized": "TN09BK5678",
            "matched_vehicle_id": vehicle_id,
        }
        mock_person = {"id": person_id, "full_name": "Alice Smith", "status": "active", "person_type": "staff"}
        mock_vehicle = {"id": vehicle_id, "plate_number": "TN09BK5678", "plate_normalized": "TN09BK5678", "status": "active", "owner_person_id": other_person_id, "owner_name": "Bob Jones"}

        with patch("app.services.access_decision_service._get_face_verification", return_value=face_ver):
            with patch("app.services.access_decision_service._get_alpr_verification", return_value=alpr_ver):
                with patch("app.services.access_decision_service._get_person", return_value=mock_person):
                    with patch("app.services.access_decision_service._get_vehicle", return_value=mock_vehicle):
                        with patch("app.services.watchlist_service.check_watchlist", return_value={"hit": False, "severity": None, "reason_code": None, "reason_text": None, "entry_id": None, "entry_reason": None}):
                            with patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "reason_code": "SCHEDULE_OK", "detail": "Open"}):
                                with patch("app.services.access_decision_service._persist_attempt", return_value=str(uuid.uuid4())):
                                    resp = evaluate_access_attempt(
                                        db=mock_db,
                                        direction="ENTRY",
                                        face_verification_id=face_ver["id"],
                                        alpr_verification_id=alpr_ver["id"],
                                        initiated_by=str(uuid.uuid4()),
                                    )
                                    assert resp["decision"] == "MANUAL_REVIEW"
                                    assert "OWNER_MISMATCH" in resp["reason_codes"]

    def test_decision_all_checks_passed_allows(self):
        mock_db = MagicMock()
        person_id = str(uuid.uuid4())
        vehicle_id = str(uuid.uuid4())

        face_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "confidence": 0.92,
            "matched_person_id": person_id,
            "faces_detected": 1,
        }
        alpr_ver = {
            "id": str(uuid.uuid4()),
            "result": "matched",
            "detected_plate": "TN09BK5678",
            "detected_plate_normalized": "TN09BK5678",
            "matched_vehicle_id": vehicle_id,
        }
        mock_person = {"id": person_id, "full_name": "Alice Smith", "status": "active", "person_type": "staff"}
        mock_vehicle = {"id": vehicle_id, "plate_number": "TN09BK5678", "plate_normalized": "TN09BK5678", "status": "active", "owner_person_id": person_id, "owner_name": "Alice Smith"}

        with patch("app.services.access_decision_service._get_face_verification", return_value=face_ver):
            with patch("app.services.access_decision_service._get_alpr_verification", return_value=alpr_ver):
                with patch("app.services.access_decision_service._get_person", return_value=mock_person):
                    with patch("app.services.access_decision_service._get_vehicle", return_value=mock_vehicle):
                        with patch("app.services.watchlist_service.check_watchlist", return_value={"hit": False, "severity": None, "reason_code": None, "reason_text": None, "entry_id": None, "entry_reason": None}):
                            with patch("app.services.schedule_service.evaluate_schedule", return_value={"ok": True, "reason_code": "SCHEDULE_OK", "detail": "Open"}):
                                with patch("app.services.access_decision_service._persist_attempt", return_value=str(uuid.uuid4())):
                                    resp = evaluate_access_attempt(
                                        db=mock_db,
                                        direction="ENTRY",
                                        face_verification_id=face_ver["id"],
                                        alpr_verification_id=alpr_ver["id"],
                                        initiated_by=str(uuid.uuid4()),
                                    )
                                    assert resp["decision"] == "ALLOW"
                                    assert "ALL_CHECKS_PASSED" in resp["reason_codes"]
                                    assert resp["gate_result"] == "OPEN"


# ---------------------------------------------------------------------------
# 5. Phase 3 API Endpoints
# ---------------------------------------------------------------------------

class TestPhase3Endpoints:
    def test_gate_status_and_reset(self, client, mock_account):
        app.dependency_overrides[require_security] = lambda: mock_account

        # Status
        res = client.get("/api/gate/status")
        assert res.status_code == 200
        assert "state" in res.json()
        state_before_reset = res.json()["state"]

        # Reset
        res_reset = client.post("/api/gate/reset")
        assert res_reset.status_code == 200
        assert res_reset.json()["hardware"]["acknowledged"] is False
        assert res_reset.json()["status"]["state"] == state_before_reset

        app.dependency_overrides.clear()

    def test_pending_reviews_endpoint(self, client, mock_account):
        app.dependency_overrides[require_security] = lambda: mock_account

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        app.dependency_overrides[get_db] = lambda: mock_db

        res = client.get("/api/access/pending-reviews")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        app.dependency_overrides.clear()
