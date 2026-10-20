"""
SmartGuard AI — IoT Microservice Configuration
Reads settings from environment variables / .env file.
"""
from functools import lru_cache
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ───────────────────────────────────────────────────────────────
    iot_service_host: str = Field(default="0.0.0.0")
    iot_service_port: int = Field(default=8001)
    iot_log_level: str = Field(default="INFO")

    # ── ESP32 Device Credentials ──────────────────────────────────────────────
    iot_device_id: str = Field(default="smartguard-esp32-01")
    iot_device_key: str = Field(default="")

    # ── Service-to-Service Authentication ─────────────────────────────────────
    # Used by the main backend when calling POST /api/v1/gate/status
    iot_service_secret: str = Field(default="")

    # ── Trusted Origins ───────────────────────────────────────────────────────
    iot_allowed_origins: str = Field(default="http://localhost:5173,http://localhost:8000")

    # ── Timing ────────────────────────────────────────────────────────────────
    iot_heartbeat_timeout_seconds: float = Field(default=30.0)
    iot_ack_timeout_seconds: float = Field(default=5.0)
    iot_auto_close_duration_ms: int = Field(default=15000)

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.iot_allowed_origins.split(",") if o.strip()]

    def validate_critical(self) -> None:
        if not self.iot_service_secret:
            raise ValueError("IOT_SERVICE_SECRET must be set")
        if len(self.iot_service_secret) < 32:
            raise ValueError("IOT_SERVICE_SECRET must be at least 32 characters")
        if not self.iot_device_key:
            raise ValueError("IOT_DEVICE_KEY must be set")


@lru_cache
def get_settings() -> Settings:
    return Settings()
