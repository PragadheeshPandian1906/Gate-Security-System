"""
SmartGuard AI — AI Verification API (Phase 2)

Endpoints:
  POST /api/ai/verify-face       - upload image → face recognition
  POST /api/ai/verify-plate      - upload image → ALPR
  GET  /api/ai/diagnostics       - AI runtime status report
  GET  /api/ai/face-history      - recent face verification log
  GET  /api/ai/alpr-history      - recent ALPR verification log
  GET  /api/ai/storage-stats     - dual storage statistics
"""
import logging
import uuid
from typing import Annotated

import time
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_active_account, require_security
from app.db.session import get_db
from app.models.account import SecurityAccount
from app.models.people import AlprVerification, FaceVerification
from app.schemas.people import (
    AlprVerificationOut,
    AlprVerifyResponse,
    FaceVerificationOut,
    FaceVerifyResponse,
    LiveFrameResponse,
    LiveFrameTiming,
    LiveFrameErrors,
)
from app.services import ai_diagnostics, face_service, storage_service
from app.services.alpr_service import run_alpr_pipeline, process_live_frame_plates

logger = logging.getLogger("smartguard.ai")
router = APIRouter(prefix="/ai", tags=["ai"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Server-side cooldown cache for auto-saving live detection frames to storage
_live_event_cooldown: dict[str, float] = {}
_LIVE_COOLDOWN_SECONDS = 8.0


# ---------------------------------------------------------------------------
# Live Frame Real-time Processing (Zero DB spam, Independent Pipelines)
# ---------------------------------------------------------------------------

@router.post("/live-frame", response_model=LiveFrameResponse)
async def process_live_frame(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
    frame_id: Annotated[str | None, Form()] = None,
    timestamp: Annotated[float | None, Form()] = None,
):
    """
    Real-time live camera frame detection endpoint.
    Performs simultaneous face detection/similarity and ALPR plate detection/OCR.
    Returns detected bounding boxes and labels without persisting every frame.
    """
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image format. Use JPEG, PNG, or WebP.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Frame exceeds 10 MB payload limit.")

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty frame received.")

    # Determine image dimensions using Pillow
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        img_w, img_h = img.size
    except Exception:
        img_w, img_h = 640, 480

    t_total_start = time.perf_counter()

    # Face pipeline execution (independent)
    t_face_start = time.perf_counter()
    try:
        faces, face_err = face_service.process_live_frame_faces(data, db)
    except Exception as exc:
        logger.error("Live frame face pipeline failed: %s", exc, exc_info=True)
        faces, face_err = [], str(exc)
    face_latency_ms = (time.perf_counter() - t_face_start) * 1000.0

    # Plate pipeline execution (independent)
    t_plate_start = time.perf_counter()
    try:
        plates, plate_err = process_live_frame_plates(data, db)
    except Exception as exc:
        logger.error("Live frame ALPR pipeline failed: %s", exc, exc_info=True)
        plates, plate_err = [], str(exc)
    plate_latency_ms = (time.perf_counter() - t_plate_start) * 1000.0

    total_latency_ms = (time.perf_counter() - t_total_start) * 1000.0

    # ── Evidence Persistence for Detected Entities ─────────────────────────
    # If any faces or plates are detected, save evidence to dual storage (local + Supabase)
    # with rate-limiting cooldown per unique detection key to avoid storage spam.
    storage_dict = None
    if faces or plates:
        now_ts = time.time()
        should_save = False
        event_keys: list[str] = []

        for f in faces:
            person = f.get("person") if isinstance(f, dict) else getattr(f, "person", None)
            person_id = (person.get("id") if isinstance(person, dict) else getattr(person, "id", None)) if person else None
            f_status = f.get("status") if isinstance(f, dict) else getattr(f, "status", "unknown")
            k = f"face_{person_id}" if person_id else f"face_{f_status}"
            if now_ts - _live_event_cooldown.get(k, 0.0) > _LIVE_COOLDOWN_SECONDS:
                should_save = True
                event_keys.append(k)

        for p in plates:
            norm = p.get("normalized_plate") if isinstance(p, dict) else getattr(p, "normalized_plate", None)
            p_status = p.get("status") if isinstance(p, dict) else getattr(p, "status", "unknown")
            k = f"plate_{norm}" if norm else f"plate_{p_status}"
            if now_ts - _live_event_cooldown.get(k, 0.0) > _LIVE_COOLDOWN_SECONDS:
                should_save = True
                event_keys.append(k)

        if should_save:
            for k in event_keys:
                _live_event_cooldown[k] = now_ts

            evt_filename = f"live_{uuid.uuid4().hex[:12]}.jpg"
            try:
                storage_res = storage_service.save_file(
                    data=data,
                    bucket="access-evidence",
                    subfolder="live_events",
                    filename=evt_filename,
                    content_type="image/jpeg",
                )
                storage_dict = storage_res.to_dict()
                logger.info(
                    "Live frame evidence stored: %s (remote_ok=%s)",
                    storage_res.storage_path or storage_res.local_path,
                    storage_res.remote_ok,
                )

                # Track logged verification IDs for access decisions
                last_face_ver_id = None
                last_alpr_ver_id = None

                # Log matched faces to face_verifications
                for f in faces:
                    _f = f if isinstance(f, dict) else vars(f)
                    _person = _f.get("person") or {}
                    _person_id = (_person.get("id") if isinstance(_person, dict) else getattr(_person, "id", None))
                    if not _person_id:
                        continue
                    try:
                        _label = _f.get("label", "")
                        _res = _f.get("status", "no_match")
                        if _res not in ('matched', 'no_match', 'low_confidence', 'error', 'no_face'):
                            _res = 'matched' if _f.get('matched') else 'no_match'
                        ver_id = str(uuid.uuid4())
                        db.execute(
                            text(
                                """
                                INSERT INTO face_verifications
                                  (id, result, confidence, distance, matched_person_id,
                                   query_image_path, query_image_storage_path,
                                   faces_detected, meta, verified_by, timestamp)
                                VALUES
                                  (:id, :result, :confidence, :distance, :person_id,
                                   :img_path, :img_storage,
                                   :faces, CAST(:meta AS json), :verified_by, now())
                                """
                            ),
                            {
                                "id": ver_id,
                                "result": _res,
                                "confidence": _f.get("score"),
                                "distance": _f.get("distance"),
                                "person_id": _person_id,
                                "img_path": storage_res.local_path,
                                "img_storage": storage_res.storage_path,
                                "faces": len(faces),
                                "meta": f'{{"label": "{_label}"}}',
                                "verified_by": str(account.id),
                            },
                        )
                        db.commit()
                        last_face_ver_id = ver_id
                    except Exception as exc:
                        logger.debug("Live face audit log skipped: %s", exc)
                        db.rollback()

                # Log detected plates to alpr_verifications
                for p in plates:
                    _p = p if isinstance(p, dict) else vars(p)
                    _norm = _p.get("normalized_plate")
                    if not _norm:
                        continue
                    _vehicle = _p.get("vehicle") or {}
                    _vehicle_id = (_vehicle.get("id") if isinstance(_vehicle, dict) else getattr(_vehicle, "id", None))
                    try:
                        _p_status = _p.get("status", "no_match")
                        _res = "matched" if _p.get("registered") or _p_status in ("registered", "flagged") else "no_match"
                        ver_id = str(uuid.uuid4())
                        db.execute(
                            text(
                                """
                                INSERT INTO alpr_verifications
                                  (id, result, detected_plate, detected_plate_normalized,
                                   ocr_confidence, detection_confidence, matched_vehicle_id,
                                   query_image_path, query_image_storage_path,
                                   verified_by, timestamp)
                                VALUES
                                  (:id, :result, :plate, :plate_norm,
                                   :ocr_conf, :det_conf, :vehicle_id,
                                   :img_path, :img_storage,
                                   :verified_by, now())
                                """
                            ),
                            {
                                "id": ver_id,
                                "result": _res,
                                "plate": _p.get("plate_text"),
                                "plate_norm": _norm,
                                "ocr_conf": _p.get("ocr_confidence"),
                                "det_conf": _p.get("detection_confidence"),
                                "vehicle_id": _vehicle_id,
                                "img_path": storage_res.local_path,
                                "img_storage": storage_res.storage_path,
                                "verified_by": str(account.id),
                            },
                        )
                        db.commit()
                        last_alpr_ver_id = ver_id
                    except Exception as exc:
                        logger.debug("Live plate audit log skipped: %s", exc)
                        db.rollback()
            except Exception as store_err:
                logger.warning("Failed saving live frame evidence: %s", store_err)

    return LiveFrameResponse(
        frame_id=frame_id or str(uuid.uuid4()),
        timestamp=timestamp or time.time(),
        image_width=img_w,
        image_height=img_h,
        faces=faces,
        plates=plates,
        timing=LiveFrameTiming(
            total_latency_ms=round(total_latency_ms, 2),
            face_latency_ms=round(face_latency_ms, 2),
            plate_latency_ms=round(plate_latency_ms, 2),
        ),
        errors=LiveFrameErrors(
            face_error=face_err,
            plate_error=plate_err,
        ),
        storage=storage_dict,
        face_verification_id=last_face_ver_id if 'last_face_ver_id' in locals() else None,
        alpr_verification_id=last_alpr_ver_id if 'last_alpr_ver_id' in locals() else None,
    )


# ---------------------------------------------------------------------------
# Manual Camera Snapshot Capture (Direct Dual-Storage Save)
# ---------------------------------------------------------------------------

@router.post("/save-snapshot")
async def save_camera_snapshot(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
    note: Annotated[str | None, Form()] = None,
):
    """
    Explicitly save a camera snapshot to dual storage (local + Supabase Storage).
    Triggered manually by security officer on the live terminal.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty frame payload")

    filename = f"snapshot_{uuid.uuid4().hex[:12]}.jpg"
    res = storage_service.save_file(
        data=data,
        bucket="access-evidence",
        subfolder="live_snapshots",
        filename=filename,
        content_type="image/jpeg",
    )
    return {
        "success": True,
        "filename": filename,
        "storage_path": res.storage_path,
        "local_path": res.local_path,
        "local_ok": res.local_ok,
        "remote_ok": res.remote_ok,
    }


# ---------------------------------------------------------------------------
# Face Verification
# ---------------------------------------------------------------------------

@router.post("/verify-face", response_model=FaceVerifyResponse)
async def verify_face(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Upload an image → detect face → search pgvector embeddings → return match result.
    Saves the query image to dual storage and logs the result to face_verifications.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    # Save query image
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"verify_{uuid.uuid4().hex}.{ext}"
    storage_result = storage_service.save_file(
        data=data,
        bucket="access-evidence",
        subfolder="face_queries",
        filename=filename,
        content_type=file.content_type or "image/jpeg",
    )

    # Detect + embed
    detection = face_service.detect_and_embed(data)
    faces_detected = detection.get("faces_detected", 0)

    if not detection["success"]:
        result_code = "error"
        confidence = None
        distance = None
        matched_person = None
        candidates = []
        search_result = {}
        error_msg = detection.get("error", "Detection failed")
    elif faces_detected == 0:
        result_code = "no_face"
        confidence = None
        distance = None
        matched_person = None
        candidates = []
        search_result = {}
        error_msg = None
    else:
        embedding = detection["embeddings"][0]
        search_result = face_service.search_face(embedding, db)
        result_code = search_result["result"]
        confidence = search_result.get("confidence")
        distance = search_result.get("distance")
        error_msg = search_result.get("error")
        candidates = search_result.get("candidates", [])
        if search_result.get("person_id"):
            matched_person = {
                "id": search_result["person_id"],
                "name": search_result["person_name"],
            }
        else:
            matched_person = None

    # Log to face_verifications
    verification_id = None
    try:
        log_id = uuid.uuid4()
        db.execute(
            text(
                """
                INSERT INTO face_verifications
                  (id, result, confidence, distance, matched_person_id,
                   query_image_path, query_image_storage_path,
                   faces_detected, meta, verified_by, timestamp)
                VALUES
                  (:id, :result, :confidence, :distance, :person_id,
                   :img_path, :img_storage,
                   :faces, CAST(:meta AS json), :verified_by, now())
                """
            ),
            {
                "id": str(log_id),
                "result": result_code,
                "confidence": confidence,
                "distance": distance,
                "person_id": matched_person["id"] if matched_person else None,
                "img_path": storage_result.local_path,
                "img_storage": storage_result.storage_path,
                "faces": faces_detected,
                "meta": f'{{"bboxes": {str(detection.get("bounding_boxes", [])).replace(chr(39), chr(34))}}}',
                "verified_by": str(account.id),
            },
        )
        db.commit()
        verification_id = str(log_id)
    except Exception as exc:
        logger.error("Face verification log failed: %s", exc)
        db.rollback()

    return FaceVerifyResponse(
        result=result_code,
        confidence=confidence,
        distance=distance,
        matched_person=matched_person,
        faces_detected=faces_detected,
        candidates=candidates,
        verification_id=verification_id,
        storage=storage_result.to_dict(),
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# ALPR Verification
# ---------------------------------------------------------------------------

@router.post("/verify-plate", response_model=AlprVerifyResponse)
async def verify_plate(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Upload an image → detect license plates → match DB → return result.
    Saves the query image to dual storage.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"alpr_{uuid.uuid4().hex}.{ext}"
    storage_result = storage_service.save_file(
        data=data,
        bucket="access-evidence",
        subfolder="plate_queries",
        filename=filename,
        content_type=file.content_type or "image/jpeg",
    )

    pipeline_result = run_alpr_pipeline(
        image_bytes=data,
        db=db,
        verified_by_id=str(account.id),
        image_local_path=storage_result.local_path,
        image_storage_path=storage_result.storage_path,
    )

    return AlprVerifyResponse(
        result=pipeline_result["result"],
        detected_plate=pipeline_result.get("detected_plate"),
        detected_plate_normalized=pipeline_result.get("detected_plate_normalized"),
        detection_confidence=pipeline_result.get("detection_confidence"),
        ocr_confidence=pipeline_result.get("ocr_confidence"),
        vehicle_match=pipeline_result.get("vehicle_match"),
        all_plates=pipeline_result.get("all_plates", []),
        verification_id=pipeline_result.get("verification_id"),
        storage=storage_result.to_dict(),
        error=pipeline_result.get("error"),
    )


# ---------------------------------------------------------------------------
# AI Diagnostics
# ---------------------------------------------------------------------------

@router.get("/diagnostics")
def get_diagnostics(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return AI runtime diagnostics: GPU, ONNX, InsightFace, FastALPR."""
    return ai_diagnostics.get_ai_diagnostics()


# ---------------------------------------------------------------------------
# Verification History
# ---------------------------------------------------------------------------

@router.get("/face-history", response_model=list[FaceVerificationOut])
def face_history(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    limit: int = Query(default=20, ge=1, le=100),
):
    """Recent face verification log entries."""
    rows = db.execute(
        select(FaceVerification).order_by(FaceVerification.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [FaceVerificationOut.model_validate(r) for r in rows]


@router.get("/alpr-history", response_model=list[AlprVerificationOut])
def alpr_history(
    db: Annotated[Session, Depends(get_db)],
    _account: Annotated[SecurityAccount, Depends(require_security)],
    limit: int = Query(default=20, ge=1, le=100),
):
    """Recent ALPR verification log entries."""
    rows = db.execute(
        select(AlprVerification).order_by(AlprVerification.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [AlprVerificationOut.model_validate(r) for r in rows]


@router.get("/storage-stats")
def storage_stats(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """Return dual-storage statistics."""
    return storage_service.get_storage_stats()


@router.get("/storage-test")
def storage_test(
    _account: Annotated[SecurityAccount, Depends(require_security)],
):
    """
    Perform a live probe upload/delete against Supabase Storage to verify
    cloud connectivity end-to-end. Safe to call at any time.
    """
    return storage_service.test_supabase_connection()
