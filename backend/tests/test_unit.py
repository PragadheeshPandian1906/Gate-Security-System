"""
SmartGuard AI — Unit Tests

Tests that do not require a live database connection.
All database calls are mocked.
"""
import uuid
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Set a dummy JWT secret before importing app modules
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-chars-long!!")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")


# ---------------------------------------------------------------------------
# 1. Security module — password hashing
# ---------------------------------------------------------------------------
class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        from app.core.security import hash_password
        pw = "MySecurePassword123!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert len(hashed) > 20

    def test_verify_correct_password(self):
        from app.core.security import hash_password, verify_password
        pw = "MySecurePassword123!"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_verify_never_raises(self):
        from app.core.security import verify_password
        # Should not raise on garbage input
        result = verify_password("password", "not-a-valid-hash")
        assert result is False


# ---------------------------------------------------------------------------
# 2. JWT module
# ---------------------------------------------------------------------------
class TestJWT:
    def test_create_and_decode(self):
        from app.core.security import create_access_token, decode_access_token
        account_id = str(uuid.uuid4())
        token = create_access_token(subject=account_id, extra_claims={"role": "ADMIN"})
        payload = decode_access_token(token)
        assert payload["sub"] == account_id
        assert payload["role"] == "ADMIN"
        assert "exp" in payload

    def test_invalid_token_raises(self):
        from app.core.security import decode_access_token
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")

    def test_tampered_token_raises(self):
        from app.core.security import create_access_token, decode_access_token
        from jose import JWTError
        token = create_access_token(subject="test-id")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_access_token(tampered)

    def test_token_does_not_contain_sensitive_fields(self):
        from app.core.security import create_access_token, decode_access_token
        token = create_access_token(subject="user-123", extra_claims={"role": "SECURITY"})
        payload = decode_access_token(token)
        # These must never appear in token claims
        assert "password" not in payload
        assert "password_hash" not in payload
        assert "secret" not in payload


# ---------------------------------------------------------------------------
# 3. Account service — unit tests with mocked repository
# ---------------------------------------------------------------------------
class TestAccountServiceUnit:
    def _make_service_with_mock_repo(self, mock_repo):
        """Create an AccountService backed by a mock session + mock repo."""
        from app.services.account_service import AccountService
        mock_db = MagicMock()
        service = AccountService(mock_db)
        service._repo = mock_repo
        return service

    def test_authenticate_valid_credentials(self):
        from app.core.security import hash_password
        from app.models.account import SecurityAccount
        from app.services.account_service import AccountService

        account = SecurityAccount(
            id=uuid.uuid4(),
            username="admin",
            password_hash=hash_password("GoodPass1!"),
            full_name="Admin User",
            role="ADMIN",
            status="active",
            must_change_password=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = account
        service = self._make_service_with_mock_repo(mock_repo)

        result = service.authenticate("admin", "GoodPass1!")
        assert result.username == "admin"

    def test_authenticate_wrong_password(self):
        from app.core.security import hash_password
        from app.models.account import SecurityAccount
        from app.services.account_service import AccountService, AuthenticationError

        account = SecurityAccount(
            id=uuid.uuid4(),
            username="admin",
            password_hash=hash_password("correct"),
            full_name="Admin User",
            role="ADMIN",
            status="active",
            must_change_password=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = account
        service = self._make_service_with_mock_repo(mock_repo)

        with pytest.raises(AuthenticationError):
            service.authenticate("admin", "wrong")

    def test_authenticate_nonexistent_user(self):
        from app.services.account_service import AccountService, AuthenticationError
        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = None
        service = self._make_service_with_mock_repo(mock_repo)

        with pytest.raises(AuthenticationError):
            service.authenticate("unknown", "any")

    def test_authenticate_inactive_account(self):
        from app.core.security import hash_password
        from app.models.account import SecurityAccount
        from app.services.account_service import AccountService, AuthenticationError

        account = SecurityAccount(
            id=uuid.uuid4(),
            username="inactive",
            password_hash=hash_password("GoodPass1!"),
            full_name="Inactive",
            role="SECURITY",
            status="inactive",
            must_change_password=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = account
        service = self._make_service_with_mock_repo(mock_repo)

        with pytest.raises(AuthenticationError):
            service.authenticate("inactive", "GoodPass1!")

    def test_bootstrap_fails_when_admin_exists(self):
        from app.services.account_service import AccountService
        mock_repo = MagicMock()
        mock_repo.exists_any_admin.return_value = True
        service = self._make_service_with_mock_repo(mock_repo)

        with pytest.raises(ValueError, match="already exists"):
            service.bootstrap_admin("admin", "password123", "Admin")

    def test_bootstrap_fails_on_duplicate_username(self):
        from app.models.account import SecurityAccount
        from app.core.security import hash_password
        from app.services.account_service import AccountService

        existing = SecurityAccount(
            id=uuid.uuid4(),
            username="admin",
            password_hash=hash_password("pw"),
            full_name="Existing",
            role="SECURITY",
            status="active",
            must_change_password=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_repo = MagicMock()
        mock_repo.exists_any_admin.return_value = False
        mock_repo.get_by_username.return_value = existing
        service = self._make_service_with_mock_repo(mock_repo)

        with pytest.raises(ValueError, match="already taken"):
            service.bootstrap_admin("admin", "password123", "Admin")


# ---------------------------------------------------------------------------
# 4. Health endpoint — liveness (no DB needed)
# ---------------------------------------------------------------------------
class TestLiveness:
    def test_live_returns_ok(self):
        """Liveness endpoint should always return 200 regardless of DB state."""
        from app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# 5. Auth endpoints — with mocked DB dependency
# ---------------------------------------------------------------------------
class TestAuthEndpoints:
    @pytest.fixture(autouse=True)
    def setup_env(self):
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-at-least-32-chars-long!!"
        os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"

    def _make_client_with_mock_account(self, account, mock_db_session):
        """Override get_db with a mock that returns mock_db_session."""
        from app.main import app
        from app.db.session import get_db
        from fastapi.testclient import TestClient

        def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        return client

    def test_login_invalid_credentials_returns_401(self):
        from app.main import app
        from app.db.session import get_db
        from fastapi.testclient import TestClient
        from app.services.account_service import AccountService, AuthenticationError

        mock_db = MagicMock()

        def override_get_db():
            yield mock_db

        with patch.object(AccountService, "authenticate", side_effect=AuthenticationError("Invalid credentials")):
            app.dependency_overrides[get_db] = override_get_db
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/auth/login",
                    json={"username": "wrong", "password": "wrong"},
                )
            app.dependency_overrides.clear()

        assert response.status_code == 401

    def test_me_without_token_returns_403(self):
        from app.main import app
        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/auth/me")
        assert response.status_code in (401, 403)

    def test_admin_endpoint_rejects_security_role(self, security_account, security_token):
        from app.main import app
        from app.db.session import get_db
        from app.api.dependencies import get_current_account
        from fastapi.testclient import TestClient

        def override_get_db():
            yield MagicMock()

        def override_get_current_account():
            return security_account

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_account] = override_get_current_account

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/admin/accounts",
                headers={"Authorization": f"Bearer {security_token}"},
            )
        app.dependency_overrides.clear()

        assert response.status_code == 403

    def test_admin_endpoint_rejects_inactive_account(self, inactive_account):
        from app.main import app
        from app.db.session import get_db
        from app.api.dependencies import get_current_account
        from fastapi.testclient import TestClient

        def override_get_db():
            yield MagicMock()

        def override_get_current_account():
            return inactive_account

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_account] = override_get_current_account

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/admin/accounts",
                headers={"Authorization": "Bearer fake-token"},
            )
        app.dependency_overrides.clear()

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# 6. Vector handling (no DB — testing numpy/pgvector library presence)
# ---------------------------------------------------------------------------
class TestVectorSupport:
    def test_pgvector_library_importable(self):
        """pgvector library must be installable and importable."""
        import pgvector
        assert pgvector is not None

    def test_512_dim_vector_representable(self):
        """Verify we can create and work with a 512-dimensional float vector."""
        import numpy as np
        vec = np.random.rand(512).astype(np.float32)
        assert vec.shape == (512,)
        assert vec.dtype == np.float32
        # Verify it can be serialised to a list (as pgvector expects)
        as_list = vec.tolist()
        assert len(as_list) == 512
        assert all(isinstance(v, float) for v in as_list)
