"""
SmartGuard AI — FastALPR Service (Phase 2)

Provides license plate detection and OCR using the fast-alpr library.
Normalises detected plates and matches them against the vehicles table.

Design principles:
  - Lazy model initialisation (no GPU memory at startup)
  - Graceful degradation when fast-alpr is not installed
  - GPU (CUDAExecutionProvider) preferred, CPU fallback automatic
  - All operations return typed result dicts; never raise on AI errors
"""
import logging
import re
from typing import Optional

import numpy as np

logger = logging.getLogger("smartguard.alpr")

_alpr = None
_alpr_init_tried = False


def normalize_plate(plate: str) -> str:
    """
    Normalise a license plate string for database matching:
    uppercase, remove spaces / hyphens / dots.

    Example:  'TN-38 BX 4791' → 'TN38BX4791'
    """
    return re.sub(r"[\s\-\.]", "", plate.upper())


def _get_alpr():
    """Lazy-load FastALPR. Returns None if unavailable."""
    global _alpr, _alpr_init_tried
    if _alpr_init_tried:
        return _alpr
    _alpr_init_tried = True
    try:
        from fast_alpr import ALPR  # type: ignore
        from app.services.ai_diagnostics import get_execution_providers

        providers = get_execution_providers()
        logger.info("Initialising FastALPR with providers: %s", providers)

        # FastALPR uses onnxruntime models (yolo-v9 license plate detector + cct-xs OCR)
        _alpr = ALPR(
            detector_providers=providers,
            ocr_providers=providers,
        )
        logger.info("FastALPR model loaded successfully")
    except ImportError:
        logger.warning("fast-alpr not installed — ALPR disabled")
        _alpr = None
    except Exception as exc:
        logger.error("FastALPR initialisation failed: %s", exc, exc_info=True)
        _alpr = None
    return _alpr


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def detect_plates(image_bytes: bytes) -> dict:
    """
    Detect and read license plates in *image_bytes*.

    Returns:
        {
          "success": bool,
          "plates": [
            {
              "text": str | None,
              "normalized": str | None,
              "detection_confidence": float,
              "ocr_confidence": float,
              "bounding_box": [x1, y1, x2, y2],
            }, ...
          ],
          "error": str | None,
        }
    """
    alpr = _get_alpr()
    if alpr is None:
        return {
            "success": False,
            "plates": [],
            "error": "FastALPR model not available",
        }

    try:
        import cv2  # type: ignore

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {
                "success": False,
                "plates": [],
                "error": "Failed to decode image — unsupported format or corrupt data",
            }

        results = alpr.predict(img)
        plates = []
        for r in results:
            ocr = getattr(r, "ocr", None)
            det = getattr(r, "detection", None)
            bbox_obj = getattr(det, "bounding_box", None) if det else None

            if bbox_obj is not None:
                if hasattr(bbox_obj, "x1"):
                    bbox = [int(bbox_obj.x1), int(bbox_obj.y1), int(bbox_obj.x2), int(bbox_obj.y2)]
                elif isinstance(bbox_obj, (list, tuple)):
                    bbox = [int(x) for x in bbox_obj]
                else:
                    bbox = []
            else:
                bbox = []

            det_conf = float(det.confidence) if det and hasattr(det, "confidence") and det.confidence is not None else 0.0

            if ocr is None or not getattr(ocr, "text", "").strip():
                # Plate detected, but OCR unavailable or empty
                plates.append({
                    "text": None,
                    "normalized": None,
                    "detection_confidence": round(det_conf, 4),
                    "ocr_confidence": 0.0,
                    "bounding_box": bbox,
                })
            else:
                ocr_text = ocr.text.strip()
                conf_val = getattr(ocr, "confidence", 0.0)
                if isinstance(conf_val, list):
                    ocr_conf = float(sum(conf_val) / len(conf_val)) if conf_val else 0.0
                elif conf_val is not None:
                    ocr_conf = float(conf_val)
                else:
                    ocr_conf = 0.0

                plates.append({
                    "text": ocr_text,
                    "normalized": normalize_plate(ocr_text),
                    "detection_confidence": round(det_conf, 4),
                    "ocr_confidence": round(ocr_conf, 4),
                    "bounding_box": bbox,
                })

        return {"success": True, "plates": plates, "error": None}

    except Exception as exc:
        logger.error("Plate detection failed: %s", exc, exc_info=True)
        return {"success": False, "plates": [], "error": str(exc)}


def match_plate(
    detected_normalized: str,
    db,
) -> dict:
    """
    Look up *detected_normalized* against the vehicles table.

    Uses exact normalised match first; could be extended to fuzzy matching.

    Returns:
        {
          "matched": bool,
          "vehicle_id": str | None,
          "plate_number": str | None,
          "vehicle_status": str | None,
          "owner_name": str | None,
        }
    """
    try:
        from sqlalchemy import text

        row = db.execute(
            text(
                """
                SELECT id, plate_number, status, owner_name, owner_person_id, make, model, color
                FROM vehicles
                WHERE plate_normalized = :plate
                LIMIT 1
                """
            ),
            {"plate": detected_normalized},
        ).fetchone()

        if row:
            return {
                "matched": True,
                "vehicle_id": str(row.id),
                "plate_number": row.plate_number,
                "vehicle_status": row.status,
                "owner_name": row.owner_name,
                "owner_person_id": str(row.owner_person_id) if row.owner_person_id else None,
                "make": row.make,
                "model": row.model,
                "color": row.color,
            }
        return {
            "matched": False,
            "vehicle_id": None,
            "plate_number": None,
            "vehicle_status": None,
            "owner_name": None,
        }
    except Exception as exc:
        logger.error("Plate DB match failed: %s", exc, exc_info=True)
        return {
            "matched": False,
            "vehicle_id": None,
            "plate_number": None,
            "vehicle_status": None,
            "owner_name": None,
            "error": str(exc),
        }


def run_alpr_pipeline(
    image_bytes: bytes,
    db,
    verified_by_id: Optional[str] = None,
    image_local_path: Optional[str] = None,
    image_storage_path: Optional[str] = None,
) -> dict:
    """
    Full ALPR pipeline: detect plates → normalise → match DB → log result.

    Returns a comprehensive result dict and saves an alpr_verifications record.
    """
    from sqlalchemy import text

    detection = detect_plates(image_bytes)

    if not detection["success"]:
        result_code = "error"
        detected_plate = None
        detected_normalized = None
        detection_conf = None
        ocr_conf = None
        matched_vehicle_id = None
        match_info = {}
    elif not detection["plates"]:
        result_code = "no_plate"
        detected_plate = None
        detected_normalized = None
        detection_conf = None
        ocr_conf = None
        matched_vehicle_id = None
        match_info = {}
    else:
        best = max(detection["plates"], key=lambda p: p["detection_confidence"])
        detected_plate = best["text"]
        detected_normalized = best["normalized"]
        detection_conf = best["detection_confidence"]
        ocr_conf = best["ocr_confidence"]
        match_info = match_plate(detected_normalized, db)
        matched_vehicle_id = match_info.get("vehicle_id")
        result_code = "matched" if match_info.get("matched") else "no_match"

    # Persist verification log
    try:
        import uuid as _uuid
        log_id = str(_uuid.uuid4())
        db.execute(
            text(
                """
                INSERT INTO alpr_verifications
                  (id, result, detected_plate, detected_plate_normalized,
                   detection_confidence, ocr_confidence, matched_vehicle_id,
                   query_image_path, query_image_storage_path,
                   raw_detections, verified_by, timestamp)
                VALUES
                  (:id, :result, :detected_plate, :detected_normalized,
                   :det_conf, :ocr_conf, :vehicle_id,
                   :img_path, :img_storage,
                   CAST(:raw AS json), :verified_by, now())
                """
            ),
            {
                "id": log_id,
                "result": result_code,
                "detected_plate": detected_plate,
                "detected_normalized": detected_normalized,
                "det_conf": detection_conf,
                "ocr_conf": ocr_conf,
                "vehicle_id": matched_vehicle_id,
                "img_path": image_local_path,
                "img_storage": image_storage_path,
                "raw": str(detection["plates"]).replace("'", '"') if detection["plates"] else "[]",
                "verified_by": str(verified_by_id) if verified_by_id else None,
            },
        )
        db.commit()
    except Exception as exc:
        logger.error("ALPR verification log failed: %s", exc)
        db.rollback()

    return {
        "result": result_code,
        "detected_plate": detected_plate,
        "detected_plate_normalized": detected_normalized,
        "detection_confidence": detection_conf,
        "ocr_confidence": ocr_conf,
        "vehicle_match": match_info if match_info.get("matched") else None,
        "all_plates": detection.get("plates", []),
        "error": detection.get("error"),
        "verification_id": str(log_id),
    }


def process_live_frame_plates(
    image_bytes: bytes,
    db,
) -> tuple[list[dict], Optional[str]]:
    """
    Process all license plates in a live camera frame.

    Returns:
        (plates, error_message)
        where each item in plates is a dict matching LivePlateDetection schema.
    """
    detection = detect_plates(image_bytes)
    if not detection["success"]:
        return [], detection.get("error", "ALPR unavailable")

    raw_plates = detection.get("plates", [])
    if not raw_plates:
        return [], None

    plates = []
    for p in raw_plates:
        bbox = p.get("bounding_box", [])
        plate_text = p.get("text")
        normalized = p.get("normalized")
        det_conf = p.get("detection_confidence")
        ocr_conf = p.get("ocr_confidence")

        if not normalized or not plate_text:
            # Plate detected, but text unreadable
            plates.append({
                "box": bbox,
                "plate_text": None,
                "normalized_plate": None,
                "detection_confidence": round(det_conf, 4) if det_conf is not None else None,
                "ocr_confidence": 0.0,
                "registered": False,
                "status": "unreadable",
                "label": "Plate Detected | Text Unreadable",
                "vehicle": None,
            })
            continue

        # Look up in registered vehicles
        match_res = match_plate(normalized, db)
        if match_res.get("matched"):
            v_status = match_res.get("vehicle_status", "active")
            is_flagged = (v_status == "flagged")
            status = "flagged" if is_flagged else "registered"
            tag = "FLAGGED" if is_flagged else "Registered"
            label = f"{normalized} | {tag}"
            veh = {
                "id": str(match_res["vehicle_id"]),
                "plate_number": match_res.get("plate_number") or normalized,
                "status": v_status,
                "owner_name": match_res.get("owner_name"),
                "owner_person_id": match_res.get("owner_person_id"),
                "make": match_res.get("make"),
                "model": match_res.get("model"),
                "color": match_res.get("color"),
            }
            registered = True
        else:
            status = "unregistered"
            label = f"{normalized} | Unregistered"
            veh = None
            registered = False

        plates.append({
            "box": bbox,
            "plate_text": plate_text,
            "normalized_plate": normalized,
            "detection_confidence": round(det_conf, 4) if det_conf is not None else None,
            "ocr_confidence": round(ocr_conf, 4) if ocr_conf is not None else None,
            "registered": registered,
            "status": status,
            "label": label,
            "vehicle": veh,
        })

    return plates, None

