"""
SmartGuard AI — Application Configuration
Reads all settings from environment variables via pydantic-settings.
"""
from functools import lru_cache
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Ensure .env is always loaded into os.environ
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="SmartGuard AI")
    app_env: str = Field(default="development")
    api_prefix: str = Field(default="/api")
    frontend_origins: str = Field(default="http://localhost:5173")
    # Base URL for building links inside email templates (no trailing slash)
    app_base_url: str = Field(default="http://localhost:5173")

    # Database
    database_url: str = Field(default="")

    # Supabase Cloud Storage
    supabase_url: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    supabase_key: str = Field(default="")

    # JWT
    jwt_secret_key: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)

    # Logging
    log_level: str = Field(default="INFO")

    # ── IoT Gate Controller Settings ────────────────────────────────────
    iot_auto_close_duration_ms: int = Field(default=15000)
    iot_microservice_url: str = Field(default="http://localhost:8001")
    iot_service_secret: str = Field(default="")

    # ── Phase 4: Email / Notification Settings ──────────────────────────
    # Set EMAIL_ENABLED=true to activate email delivery
    email_enabled: bool = Field(default=False)
    # Provider: "brevo" (default, free tier 300/day) or "smtp"
    email_provider: str = Field(default="brevo")
    # Brevo transactional API key (starts with xkeysib-)
    email_api_key: str = Field(default="")
    # SMTP settings (alternative to Brevo)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)
    # Sender identity (must be a verified address in your email provider)
    email_from_address: str = Field(default="noreply@smartguard.local")
    email_from_name: str = Field(default="SmartGuard AI")

    @property
    def allowed_origins(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    def validate_critical(self) -> None:
        """Raise if required secrets are missing."""
        if not self.database_url:
            raise ValueError("DATABASE_URL is not configured.")
        if not self.jwt_secret_key:
            raise ValueError("JWT_SECRET_KEY is not configured.")
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")

    def validate_email_config(self) -> None:
        """Raise if email is enabled but misconfigured."""
        if not self.email_enabled:
            return
        if not self.email_from_address:
            raise ValueError("EMAIL_FROM_ADDRESS must be set when EMAIL_ENABLED=true.")
        if self.email_provider == "brevo" and not self.email_api_key:
            raise ValueError("EMAIL_API_KEY must be set when EMAIL_PROVIDER=brevo.")
        if self.email_provider == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST must be set when EMAIL_PROVIDER=smtp.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
