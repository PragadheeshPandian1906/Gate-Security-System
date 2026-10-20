"""
SmartGuard AI — Database Engine and Session Management
Provides the SQLAlchemy engine, session factory, and FastAPI dependency.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings

logger = logging.getLogger("smartguard.db")

_engine = None
_SessionLocal = None


def _build_connect_args(database_url: str) -> dict:
    """
    Return appropriate connect_args for the given database URL.
    Supabase requires SSL for direct and pooled connections.
    """
    if database_url.startswith("postgresql"):
        return {"sslmode": "require"}
    return {}


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")

        connect_args = _build_connect_args(settings.database_url)
        # Log that we are connecting, but NEVER log the full URL or credentials
        logger.info("Initialising database engine (SSL=%s)", bool(connect_args))

        _engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            pool_pre_ping=True,       # detect stale connections before use
            pool_size=4,              # kept small to stay well within Supabase's 15 client limit
            max_overflow=4,           # max 8 connections total per worker process
            pool_timeout=15,
            pool_recycle=300,         # recycle connections every 5 min to prevent stale pooler disconnects
            echo=False,               # never echo SQL (would leak data shapes to logs)
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a session per request, always closes on exit
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a scoped database session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Context-manager form — useful for CLI scripts and tests
# ---------------------------------------------------------------------------
@contextmanager
def db_session() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Connectivity and capability checks
# ---------------------------------------------------------------------------
def check_db_connectivity() -> bool:
    """Return True if the database is reachable."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connectivity verified")
        return True
    except OperationalError as exc:
        logger.error("Database connectivity check failed: %s", exc.args[0] if exc.args else "unknown")
        return False
    except Exception as exc:
        logger.error("Unexpected database error during connectivity check: %s", type(exc).__name__)
        return False


def check_pgvector() -> bool:
    """
    Return True if the pgvector extension is available.
    Does NOT attempt to enable the extension — that is done via Alembic.
    """
    try:
        with get_engine().connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
        if result:
            logger.info("pgvector extension verified")
            return True
        logger.warning("pgvector extension is not enabled in the database")
        return False
    except Exception as exc:
        logger.error("pgvector check failed: %s", type(exc).__name__)
        return False


def check_database_readiness() -> tuple[bool, bool]:
    """Check database connectivity and pgvector availability in one round trip."""
    try:
        with get_engine().connect() as conn:
            result = conn.execute(
                text(
                    "SELECT 1 AS database_ok, "
                    "EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') "
                    "AS pgvector_ok"
                )
            ).fetchone()
        if result is None:
            logger.error("Database readiness query returned no result")
            return False, False
        database_ok, pgvector_ok = bool(result[0]), bool(result[1])
        if not pgvector_ok:
            logger.warning("pgvector extension is not enabled in the database")
        return database_ok, pgvector_ok
    except Exception as exc:
        logger.error("Database readiness check failed: %s", type(exc).__name__)
        return False, False
