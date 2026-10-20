"""
SmartGuard AI — pytest configuration and shared fixtures.
Tests that require a live database are marked with @pytest.mark.integration
and are skipped when DATABASE_URL is not configured.
"""
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires live Supabase database connection")


@pytest.fixture(scope="session")
def db_available() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Application fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    """FastAPI TestClient with mocked database dependencies."""
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_db():
    """Returns a MagicMock Session for unit tests that don't need a real DB."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Security fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def admin_account():
    """An in-memory SecurityAccount with ADMIN role."""
    from app.models.account import SecurityAccount
    from app.core.security import hash_password
    from datetime import datetime, timezone
    acc = SecurityAccount(
        id=uuid.uuid4(),
        username="testadmin",
        password_hash=hash_password("SecurePass123!"),
        full_name="Test Administrator",
        role="ADMIN",
        status="active",
        must_change_password=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return acc


@pytest.fixture
def security_account():
    """An in-memory SecurityAccount with SECURITY role."""
    from app.models.account import SecurityAccount
    from app.core.security import hash_password
    from datetime import datetime, timezone
    acc = SecurityAccount(
        id=uuid.uuid4(),
        username="testsecurity",
        password_hash=hash_password("SecurePass123!"),
        full_name="Test Security Officer",
        role="SECURITY",
        status="active",
        must_change_password=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return acc


@pytest.fixture
def inactive_account():
    """An in-memory SecurityAccount with status=inactive."""
    from app.models.account import SecurityAccount
    from app.core.security import hash_password
    from datetime import datetime, timezone
    acc = SecurityAccount(
        id=uuid.uuid4(),
        username="inactiveuser",
        password_hash=hash_password("SecurePass123!"),
        full_name="Inactive User",
        role="SECURITY",
        status="inactive",
        must_change_password=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return acc


@pytest.fixture
def admin_token(admin_account):
    """A valid JWT for the admin_account fixture."""
    from app.core.security import create_access_token
    return create_access_token(
        subject=str(admin_account.id),
        extra_claims={"role": admin_account.role, "username": admin_account.username},
    )


@pytest.fixture
def security_token(security_account):
    """A valid JWT for the security_account fixture."""
    from app.core.security import create_access_token
    return create_access_token(
        subject=str(security_account.id),
        extra_claims={"role": security_account.role, "username": security_account.username},
    )
