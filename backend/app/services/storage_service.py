"""
SmartGuard AI — Dual Storage Service (Phase 2)

Manages file storage across two backends:
  1. Local filesystem  : backend/storage/  (always attempted)
  2. Supabase Storage  : private buckets    (attempted, failures are non-fatal)

Supported buckets / local directories:
  - face-images        → storage/face_images/
  - access-evidence    → storage/access_evidence/
  - visitor-qr         → storage/visitor_qr/
"""
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("smartguard.storage")

# ---------------------------------------------------------------------------
# Base storage directory (relative to backend root, resolved at import time)
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # …/backend
_STORAGE_ROOT = _BACKEND_DIR / "storage"

_BUCKET_DIR_MAP: dict[str, str] = {
    "face-images": "face_images",
    "access-evidence": "access_evidence",
    "visitor-qr": "visitor_qr",
}


def _ensure_local_dirs() -> None:
    """Create all local storage sub-directories if they do not exist."""
    for subdir in _BUCKET_DIR_MAP.values():
        (_STORAGE_ROOT / subdir).mkdir(parents=True, exist_ok=True)


_ensure_local_dirs()


# ---------------------------------------------------------------------------
# Supabase client — lazy-initialised, optional
# Only a successfully-created client is cached; failures are NOT cached so
# each call retries until the server can reach Supabase.
# ---------------------------------------------------------------------------
_supabase_client = None


def _get_supabase():
    """Return an initialised Supabase client or None if unavailable."""
    global _supabase_client
    # Return already-successful client immediately
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client  # type: ignore
        from app.core.config import get_settings

        settings = get_settings()

        # ── Resolve URL ────────────────────────────────────────────────────
        url = (
            settings.supabase_url
            or os.getenv("SUPABASE_URL", "")
        ).strip()
        if not url:
            # Derive from DATABASE_URL as a last resort
            db_url = (settings.database_url or os.getenv("DATABASE_URL", "")).strip()
            if "@db." in db_url and ".supabase.co" in db_url:
                ref = db_url.split("@db.")[1].split(".supabase.co")[0]
                url = f"https://{ref}.supabase.co"

        # ── Resolve service-role key ────────────────────────────────────────
        key = (
            settings.supabase_service_role_key
            or settings.supabase_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
            or os.getenv("SUPABASE_ANON_KEY", "")
        ).strip()

        if not url or not key:
            logger.warning(
                "storage Supabase credentials missing — "
                "url=%r key_length=%d. Cloud storage disabled.",
                url,
                len(key),
            )
            # Do NOT cache None — retry on next call in case .env is reloaded
            return None

        logger.info(
            "storage Initialising Supabase client: url=%s key_length=%d",
            url, len(key),
        )
        client = create_client(url, key)
        _supabase_client = client  # cache only on success
        logger.info("storage Supabase client initialised successfully (URL: %s)", url)
    except Exception as exc:
        # Do NOT set _supabase_client = None here — keep it unset so we retry
        logger.warning(
            "storage Supabase client init failed (will retry on next request): %s",
            exc,
            exc_info=True,
        )
        return None
    return _supabase_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class StorageResult:
    """Result of a dual-storage write operation."""
    __slots__ = ("local_path", "storage_path", "filename", "local_ok", "remote_ok")

    def __init__(
        self,
        local_path: Optional[str],
        storage_path: Optional[str],
        filename: str,
        local_ok: bool,
        remote_ok: bool,
    ):
        self.local_path = local_path
        self.storage_path = storage_path
        self.filename = filename
        self.local_ok = local_ok
        self.remote_ok = remote_ok

    def to_dict(self) -> dict:
        return {
            "local_path": self.local_path,
            "storage_path": self.storage_path,
            "filename": self.filename,
            "local_ok": self.local_ok,
            "remote_ok": self.remote_ok,
        }


def save_file(
    data: bytes,
    bucket: str,
    subfolder: str = "",
    filename: Optional[str] = None,
    content_type: str = "application/octet-stream",
) -> StorageResult:
    """
    Save *data* to local storage and attempt Supabase Storage upload.

    Args:
        data        : raw bytes to store
        bucket      : logical bucket name (e.g. 'face-images')
        subfolder   : optional subdirectory within the bucket/local dir
        filename    : optional filename; auto-generated UUID if omitted
        content_type: MIME type for Supabase upload

    Returns:
        StorageResult with paths and success flags for both backends.
    """
    if bucket not in _BUCKET_DIR_MAP:
        raise ValueError(f"Unknown storage bucket: {bucket!r}. Valid: {list(_BUCKET_DIR_MAP)}")

    if not filename:
        filename = str(uuid.uuid4())

    # ── Local save ──────────────────────────────────────────────────────────
    local_ok = False
    local_path: Optional[str] = None
    try:
        local_dir = _STORAGE_ROOT / _BUCKET_DIR_MAP[bucket]
        if subfolder:
            local_dir = local_dir / subfolder
        local_dir.mkdir(parents=True, exist_ok=True)
        full_local = local_dir / filename
        full_local.write_bytes(data)
        local_path = str(full_local)
        local_ok = True
        logger.debug("storage Local save OK: %s", local_path)
    except Exception as exc:
        logger.error("storage Local save FAILED for %s/%s: %s", bucket, filename, exc)

    # ── Supabase Storage upload ──────────────────────────────────────────────
    remote_ok = False
    storage_path: Optional[str] = None
    try:
        sb = _get_supabase()
        if sb is not None:
            remote_key = f"{subfolder}/{filename}" if subfolder else filename
            try:
                sb.storage.from_(bucket).upload(
                    remote_key,
                    data,
                    {"content-type": content_type, "x-upsert": "true"},
                )
                storage_path = f"{bucket}/{remote_key}"
                remote_ok = True
                logger.info("storage Supabase upload OK: %s", storage_path)
            except Exception as up_err:
                err_str = str(up_err).lower()
                # If bucket doesn't exist, try to create it automatically
                if "bucket not found" in err_str or "not_found" in err_str:
                    try:
                        logger.info("storage Bucket '%s' not found, creating bucket in Supabase...", bucket)
                        sb.storage.create_bucket(bucket, options={"public": False})
                        sb.storage.from_(bucket).upload(
                            remote_key,
                            data,
                            {"content-type": content_type, "x-upsert": "true"},
                        )
                        storage_path = f"{bucket}/{remote_key}"
                        remote_ok = True
                        logger.info("storage Created bucket and uploaded successfully: %s", storage_path)
                    except Exception as create_err:
                        logger.warning("storage Failed to auto-create bucket '%s': %s", bucket, create_err)
                else:
                    logger.warning("storage Supabase upload failed (non-fatal): %s", up_err)
    except Exception as exc:
        logger.warning("storage Supabase storage operation error: %s", exc)

    return StorageResult(
        local_path=local_path,
        storage_path=storage_path,
        filename=filename,
        local_ok=local_ok,
        remote_ok=remote_ok,
    )


def read_local_file(local_path: str) -> Optional[bytes]:
    """Read a file from local storage. Returns None if not found."""
    try:
        return Path(local_path).read_bytes()
    except FileNotFoundError:
        logger.warning("storage File not found: %s", local_path)
        return None
    except Exception as exc:
        logger.error("storage Read failed: %s", exc)
        return None


def delete_local_file(local_path: str) -> bool:
    """Delete a file from local storage. Returns True on success."""
    try:
        Path(local_path).unlink(missing_ok=True)
        return True
    except Exception as exc:
        logger.error("storage Delete failed: %s", exc)
        return False


def test_supabase_connection() -> dict:
    """
    Perform a live probe upload to Supabase Storage to verify credentials work.
    Uploads a 1-byte file and immediately deletes it.
    Returns a dict with keys: ok (bool), error (str|None), url (str|None).
    """
    sb = _get_supabase()
    if sb is None:
        return {"ok": False, "error": "Supabase client not initialised (check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env)", "url": None}
    probe_key = f".probe/{uuid.uuid4().hex}.bin"
    try:
        sb.storage.from_("access-evidence").upload(
            probe_key,
            b"\x00",
            {"content-type": "application/octet-stream", "x-upsert": "true"},
        )
        # Clean up the probe file
        try:
            sb.storage.from_("access-evidence").remove([probe_key])
        except Exception:
            pass
        return {"ok": True, "error": None, "url": None}
    except Exception as exc:
        err = str(exc)
        logger.warning("storage Supabase probe failed: %s", err)
        return {"ok": False, "error": err, "url": None}


def get_storage_stats() -> dict:
    """Return storage statistics for monitoring."""
    stats = {}
    for bucket, subdir in _BUCKET_DIR_MAP.items():
        d = _STORAGE_ROOT / subdir
        try:
            files = list(d.glob("**/*"))
            file_list = [f for f in files if f.is_file()]
            total_bytes = sum(f.stat().st_size for f in file_list)
            stats[bucket] = {"file_count": len(file_list), "total_bytes": total_bytes}
        except Exception:
            stats[bucket] = {"file_count": 0, "total_bytes": 0}
    stats["supabase_available"] = _get_supabase() is not None
    return stats
