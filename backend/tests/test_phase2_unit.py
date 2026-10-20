"""
SmartGuard AI — Phase 2 Unit Tests

Tests for Phase 2:
- Plate normalization and vehicle schemas
- Campus person validation and face profile schemas
- Dual storage service
- AI diagnostics reporting
- AI verification endpoints with dependency overrides
"""
import io
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch

from app.main import app
from app.db.session import get_db
from app.api.dependencies import require_security, get_active_account
from app.models.account import SecurityAccount
from app.models.people import CampusPerson, Vehicle
from app.schemas.people import (
    CampusPersonCreate,
    CampusPersonUpdate,
    VehicleCreate,
    VehicleUpdate,
)
from app.services.alpr_service import normalize_plate
from app.services.storage_service import save_file, StorageResult
from app.services.ai_diagnostics import get_ai_diagnostics


# ---------------------------------------------------------------------------
# 1. License Plate Normalization
# ---------------------------------------------------------------------------
class TestLicensePlateNormalization:
    def test_plate_uppercase_and_trim(self):
        assert normalize_plate("mh-12-ab-1234") == "MH12AB1234"
        assert normalize_plate("  dl 1c a 1234 ") == "DL1CA1234"
        assert normalize_plate("ka-01-mj-9999") == "KA01MJ9999"

    def test_plate_schema_validation(self):
        payload = VehicleCreate(
            plate_number="tn 09 bk 5678",
            vehicle_type="four_wheeler",
            make="Hyundai",
            model="Creta",
            color="White",
        )
        assert payload.plate_number == "tn 09 bk 5678"
        assert normalize_plate(payload.plate_number) == "TN09BK5678"

    def test_empty_plate_raises_error(self):
        with pytest.raises(Exception):
            VehicleCreate(
                plate_number="",
                vehicle_type="two_wheeler",
            )


# ---------------------------------------------------------------------------
# 2. Campus Person Schemas
# ---------------------------------------------------------------------------
class TestCampusPersonSchemas:
    def test_valid_person_creation_schema(self):
        person_in = CampusPersonCreate(
            full_name="Dr. Alan Turing",
            person_type="staff",
            employee_id="EMP-0042",
            email="alan.turing@smartguard.campus",
            department="Computer Science",
        )
        assert person_in.full_name == "Dr. Alan Turing"
        assert person_in.employee_id == "EMP-0042"
        assert person_in.person_type == "staff"

    def test_invalid_person_type_raises(self):
        with pytest.raises(Exception):
            CampusPersonCreate(
                full_name="Invalid Type Person",
                person_type="alien",
            )

    def test_person_update_partial(self):
        update = CampusPersonUpdate(department="Robotics Lab")
        assert update.department == "Robotics Lab"
        assert update.full_name is None


# ---------------------------------------------------------------------------
# 3. Dual Storage Service
# ---------------------------------------------------------------------------
class TestStorageService:
    def test_save_local_file(self):
        dummy_content = b"fake-jpeg-image-data-header"
        filename = f"test_{uuid.uuid4().hex[:8]}.jpg"

        result = save_file(
            data=dummy_content,
            bucket="face-images",
            subfolder="test_enrollments",
            filename=filename,
            content_type="image/jpeg",
        )

        assert isinstance(result, StorageResult)
        assert result.local_ok is True
        assert result.local_path is not None
        assert os.path.exists(result.local_path)
        with open(result.local_path, "rb") as f:
            assert f.read() == dummy_content

        # Cleanup
        if os.path.exists(result.local_path):
            os.remove(result.local_path)

    def test_invalid_bucket_rejected(self):
        with pytest.raises(ValueError):
            save_file(
                data=b"malicious",
                bucket="unsupported-bucket",
            )


# ---------------------------------------------------------------------------
# 4. AI Diagnostics
# ---------------------------------------------------------------------------
class TestAiDiagnostics:
    def test_get_diagnostics_structure(self):
        diag = get_ai_diagnostics()
        assert "system" in diag
        assert "gpu" in diag
        assert "onnxruntime" in diag
        assert "insightface" in diag
        assert "fast_alpr" in diag
        assert "recommendation" in diag
        assert "compute_device" in diag["recommendation"]


# ---------------------------------------------------------------------------
# 5. Phase 2 API Endpoints
# ---------------------------------------------------------------------------
class TestPhase2Endpoints:
    def test_ai_diagnostics_unauthorized(self, client):
        response = client.get("/api/ai/diagnostics")
        assert response.status_code in (401, 403)

    def test_get_ai_diagnostics_endpoint(self, client, admin_account):
        def override_require_security():
            return admin_account

        def override_get_active_account():
            return admin_account

        app.dependency_overrides[require_security] = override_require_security
        app.dependency_overrides[get_active_account] = override_get_active_account

        try:
            response = client.get("/api/ai/diagnostics")
            assert response.status_code == 200
            data = response.json()
            assert "insightface" in data
            assert "fast_alpr" in data
            assert "recommendation" in data
        finally:
            app.dependency_overrides.clear()

    def test_ai_face_verify_requires_file(self, client, admin_account):
        def override_require_security():
            return admin_account

        app.dependency_overrides[require_security] = override_require_security

        try:
            response = client.post("/api/ai/verify-face")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_ai_alpr_verify_requires_file(self, client, admin_account):
        def override_require_security():
            return admin_account

        app.dependency_overrides[require_security] = override_require_security

        try:
            response = client.post("/api/ai/verify-plate")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_live_frame_unauthorized(self, client):
        response = client.post("/api/ai/live-frame")
        assert response.status_code in (401, 403)

    def test_live_frame_requires_file(self, client, admin_account):
        def override_require_security():
            return admin_account

        app.dependency_overrides[require_security] = override_require_security

        try:
            response = client.post("/api/ai/live-frame")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_live_frame_success(self, client, admin_account, mock_db):
        from app.db.session import get_db
        from PIL import Image
        import io

        def override_require_security():
            return admin_account

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_security] = override_require_security
        app.dependency_overrides[get_db] = override_get_db

        # Create a small valid test JPEG
        img = Image.new("RGB", (640, 480), color=(73, 109, 137))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        try:
            response = client.post(
                "/api/ai/live-frame",
                files={"file": ("frame.jpg", img_bytes, "image/jpeg")},
                data={"frame_id": "frame-test-123", "timestamp": "1729000000.5"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["frame_id"] == "frame-test-123"
            assert data["image_width"] == 640
            assert data["image_height"] == 480
            assert "faces" in data
            assert "plates" in data
            assert "timing" in data
            assert "total_latency_ms" in data["timing"]
            assert "face_latency_ms" in data["timing"]
            assert "plate_latency_ms" in data["timing"]
            assert "errors" in data
        finally:
            app.dependency_overrides.clear()

    def test_create_vehicle_with_owner_person_mapping(self, client, admin_account, mock_db):
        from datetime import datetime, timezone
        from app.api.dependencies import require_admin
        from app.db.session import get_db
        from app.models.people import CampusPerson

        # Create mock person in session
        test_person = CampusPerson(
            id=uuid.uuid4(),
            full_name="Dr. Alan Grant",
            person_type="staff",
            department="Paleontology",
            status="active",
        )
        # Mock DB behavior: plate does not exist, get returns test_person
        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        mock_db.get.return_value = test_person

        def fake_add(v):
            if getattr(v, "id", None) is None:
                v.id = uuid.uuid4()
            if getattr(v, "created_at", None) is None:
                v.created_at = datetime.now(timezone.utc)
            if getattr(v, "updated_at", None) is None:
                v.updated_at = datetime.now(timezone.utc)

        mock_db.add.side_effect = fake_add

        def override_require_admin():
            return admin_account

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_admin] = override_require_admin
        app.dependency_overrides[get_db] = override_get_db

        try:
            plate = f"TN-01-AB-{uuid.uuid4().hex[:4].upper()}"
            response = client.post(
                "/api/vehicles",
                json={
                    "plate_number": plate,
                    "make": "Jeep",
                    "model": "Wrangler",
                    "owner_person_id": str(test_person.id),
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["plate_number"] == plate
            assert data["owner_person_id"] == str(test_person.id)
            # Auto-filled from person's full_name
            assert data["owner_name"] == "Dr. Alan Grant"
        finally:
            app.dependency_overrides.clear()

