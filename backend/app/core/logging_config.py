"""
SmartGuard AI — Logging Configuration
Configures structured logging for all backend modules.
"""
import logging
import sys
from app.core.config import get_settings


def configure_logging() -> None:
    """Configure application-wide logging. Call once at startup."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Root smartguard logger — all child loggers inherit this configuration
    root_logger = logging.getLogger("smartguard")
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False

    # Silence noisy third-party loggers in production
    if not settings.is_development:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    else:
        # Show SQL in development for debugging (not credentials)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root_logger.info("Logging initialised at level %s", settings.log_level.upper())
