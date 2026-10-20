"""
SmartGuard AI — Pydantic Schemas for Authentication and Accounts
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Account username")
    password: str = Field(..., min_length=1, description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: "AccountPublic"


class AccountPublic(BaseModel):
    """Safe representation — never includes password_hash."""
    id: uuid.UUID
    username: str
    full_name: str
    role: str
    status: str
    must_change_password: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Account management schemas (admin-only operations)
# ---------------------------------------------------------------------------
class AccountCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=128)
    role: str = Field(default="SECURITY")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"ADMIN", "SECURITY"}
        if v.upper() not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v.upper()


class AccountStatusUpdate(BaseModel):
    status: str = Field(..., description="'active' or 'inactive'")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"active", "inactive"}
        if v.lower() not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v.lower()


class PasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)
    must_change_password: bool = Field(
        default=True,
        description="Force the account to change password on next login",
    )


class AccountListResponse(BaseModel):
    accounts: list[AccountPublic]
    total: int


# ---------------------------------------------------------------------------
# Health schemas
# ---------------------------------------------------------------------------
class LivenessResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    database: bool
    pgvector: bool
    environment: Optional[str] = None
