"""
SmartGuard AI — InsightFace Service (Phase 2)

Provides face detection, embedding extraction, enrollment, and
pgvector-based nearest-neighbour matching using the InsightFace
buffalo_l model (ArcFace, 512-dim embeddings).

Design principles:
  - Lazy model initialisation (no GPU memory at startup)
  - Graceful degradation when InsightFace is not installed
  - All operations return typed result dicts; never raise on AI errors
  - GPU (CUDAExecutionProvider) preferred, CPU fallback automatic
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("smartguard.insightface")

# Confidence threshold: cosine similarity ≥ this → "matched"
FACE_MATCH_THRESHOLD = 0.45
# Cosine similarity ≥ this but < MATCH → "low_confidence"
LOW_CONFIDENCE_THRESHOLD = 0.30

_app = None          # InsightFace FaceAnalysis instance
_app_init_tried = False


def _get_face_app():
    """Lazy-load InsightFace FaceAnalysis. Returns None if unavailable."""
    global _app, _app_init_tried
    if _app_init_tried:
        return _app
    _app_init_tried = True
    try:
        import insightface  # type: ignore
        from insightface.app import FaceAnalysis  # type: ignore
        from app.services.ai_diagnostics import get_execution_providers

        providers = get_execution_providers()
        logger.info("Initialising InsightFace with providers: %s", providers)

        _app = FaceAnalysis(
            name="buffalo_l",
            providers=providers,
        )
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace buffalo_l model loaded successfully")
    except ImportError:
        logger.warning("InsightFace not installed — face recognition disabled")
        _app = None
    except Exception as exc:
        logger.error("InsightFace initialisation failed: %s", exc)
        _app = None
    return _app


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def detect_and_embed(image_bytes: bytes) -> dict:
    """
    Detect faces in *image_bytes* and extract ArcFace embeddings.

    Returns:
        {
          "success": bool,
          "faces_detected": int,
          "embeddings": list[list[float]],   # len 512 each
          "bounding_boxes": list[list[int]], # [x1, y1, x2, y2]
          "landmarks": list,                 # 5-point facial landmarks
          "error": str | None,
        }
    """
    app = _get_face_app()
    if app is None:
        return {
            "success": False,
            "faces_detected": 0,
            "embeddings": [],
            "bounding_boxes": [],
            "landmarks": [],
            "error": "InsightFace model not available",
        }

    try:
        import cv2  # type: ignore  # shipped with insightface deps

        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {
                "success": False,
                "faces_detected": 0,
                "embeddings": [],
                "bounding_boxes": [],
                "landmarks": [],
                "error": "Failed to decode image — unsupported format or corrupt data",
            }

        faces = app.get(img)
        embeddings = []
        bboxes = []
        landmarks = []
        for face in faces:
            if face.embedding is not None:
                embeddings.append(face.embedding.tolist())
            bbox = face.bbox.astype(int).tolist() if face.bbox is not None else []
            bboxes.append(bbox)
            kps = face.kps.tolist() if face.kps is not None else []
            landmarks.append(kps)

        return {
            "success": True,
            "faces_detected": len(faces),
            "embeddings": embeddings,
            "bounding_boxes": bboxes,
            "landmarks": landmarks,
            "error": None,
        }
    except Exception as exc:
        logger.error("Face detection failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "faces_detected": 0,
            "embeddings": [],
            "bounding_boxes": [],
            "landmarks": [],
            "error": str(exc),
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (range −1 to 1)."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def search_face(
    query_embedding: list[float],
    db,
    top_k: int = 5,
) -> dict:
    """
    Find the closest registered face profile using pgvector cosine distance.

    Args:
        query_embedding : 512-dim embedding from detect_and_embed()
        db              : SQLAlchemy Session
        top_k           : number of candidates to retrieve

    Returns:
        {
          "matched": bool,
          "result": "matched" | "no_match" | "low_confidence",
          "confidence": float,
          "distance": float,
          "person_id": str | None,
          "person_name": str | None,
          "candidates": list[dict],
        }
    """
    from sqlalchemy import text
    from app.models.people import CampusPerson

    try:
        # pgvector cosine distance operator: <=>
        sql = text(
            """
            SELECT fp.id, fp.person_id, fp.embedding,
                   cp.full_name, cp.person_type, cp.status,
                   (fp.embedding <=> CAST(:emb AS vector)) AS distance
            FROM face_profiles fp
            JOIN campus_people cp ON cp.id = fp.person_id
            WHERE cp.status = 'active'
            ORDER BY fp.embedding <=> CAST(:emb AS vector)
            LIMIT :top_k
            """
        )
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        rows = db.execute(sql, {"emb": vec_str, "top_k": top_k}).fetchall()

        if not rows:
            return {
                "matched": False,
                "result": "no_match",
                "confidence": 0.0,
                "distance": 1.0,
                "person_id": None,
                "person_name": None,
                "candidates": [],
            }

        best = rows[0]
        # pgvector cosine distance: 0 = identical, 1 = orthogonal, 2 = opposite
        # Convert to similarity: similarity = 1 - distance  (range −1 to 1)
        best_distance = float(best.distance)
        confidence = 1.0 - best_distance  # cosine similarity

        candidates = [
            {
                "person_id": str(row.person_id),
                "person_name": row.full_name,
                "person_type": row.person_type,
                "distance": float(row.distance),
                "confidence": 1.0 - float(row.distance),
            }
            for row in rows
        ]

        if confidence >= FACE_MATCH_THRESHOLD:
            result = "matched"
            matched = True
        elif confidence >= LOW_CONFIDENCE_THRESHOLD:
            result = "low_confidence"
            matched = False
        else:
            result = "no_match"
            matched = False

        return {
            "matched": matched,
            "result": result,
            "confidence": round(confidence, 4),
            "distance": round(best_distance, 4),
            "person_id": str(best.person_id) if matched or result == "low_confidence" else None,
            "person_name": best.full_name if matched or result == "low_confidence" else None,
            "candidates": candidates,
        }

    except Exception as exc:
        logger.error("pgvector face search failed: %s", exc, exc_info=True)
        return {
            "matched": False,
            "result": "error",
            "confidence": 0.0,
            "distance": 1.0,
            "person_id": None,
            "person_name": None,
            "candidates": [],
            "error": str(exc),
        }


def enroll_face(
    person_id: str,
    image_bytes: bytes,
    db,
    enrolled_by_id: Optional[str] = None,
    image_local_path: Optional[str] = None,
    image_storage_path: Optional[str] = None,
) -> dict:
    """
    Detect face in image, extract embedding, and store in face_profiles.

    Returns:
        {
          "success": bool,
          "profile_id": str | None,
          "faces_detected": int,
          "error": str | None,
        }
    """
    detection = detect_and_embed(image_bytes)
    if not detection["success"]:
        return {
            "success": False,
            "profile_id": None,
            "faces_detected": 0,
            "error": detection.get("error", "Detection failed"),
        }

    if detection["faces_detected"] == 0:
        return {
            "success": False,
            "profile_id": None,
            "faces_detected": 0,
            "error": "No face detected in the provided image",
        }

    if detection["faces_detected"] > 1:
        logger.warning(
            "enroll_face: %d faces detected — using the largest/most prominent face",
            detection["faces_detected"],
        )

    # Use the first embedding (InsightFace sorts by detection score)
    embedding = detection["embeddings"][0]

    try:
        from sqlalchemy import text
        from app.models.people import FaceProfile

        profile_id = uuid.uuid4()
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

        # Insert using raw SQL so pgvector receives the correct type
        sql = text(
            """
            INSERT INTO face_profiles
              (id, person_id, embedding, embedding_model,
               image_path, image_storage_path, is_primary,
               created_at, enrolled_by)
            VALUES
              (:id, :person_id, CAST(:embedding AS vector), :model,
               :image_path, :image_storage_path, true,
               now(), :enrolled_by)
            """
        )
        db.execute(sql, {
            "id": str(profile_id),
            "person_id": str(person_id),
            "embedding": vec_str,
            "model": "buffalo_l",
            "image_path": image_local_path,
            "image_storage_path": image_storage_path,
            "enrolled_by": str(enrolled_by_id) if enrolled_by_id else None,
        })
        db.commit()
        logger.info("Face enrolled: profile_id=%s person_id=%s", profile_id, person_id)
        return {
            "success": True,
            "profile_id": str(profile_id),
            "faces_detected": detection["faces_detected"],
            "error": None,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Face enrollment DB write failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "profile_id": None,
            "faces_detected": detection["faces_detected"],
            "error": str(exc),
        }


def process_live_frame_faces(
    image_bytes: bytes,
    db,
    match_threshold: float = FACE_MATCH_THRESHOLD,
) -> tuple[list[dict], Optional[str]]:
    """
    Process all faces in a live camera frame.

    Returns:
        (faces, error_message)
        where each item in faces is a dict matching LiveFaceDetection schema.
    """
    from sqlalchemy import text

    detection = detect_and_embed(image_bytes)
    if not detection["success"]:
        return [], detection.get("error", "Face detection unavailable")

    faces_detected = detection.get("faces_detected", 0)
    if faces_detected == 0:
        return [], None

    bboxes = detection.get("bounding_boxes", [])
    embeddings = detection.get("embeddings", [])

    # Check if there are any enrolled profiles in DB
    has_enrolled = False
    try:
        row = db.execute(text("SELECT EXISTS (SELECT 1 FROM face_profiles LIMIT 1)")).fetchone()
        has_enrolled = bool(row[0]) if row else False
    except Exception as exc:
        logger.warning("Could not check enrolled face profiles: %s", exc)
        has_enrolled = False

    faces = []
    for i, bbox in enumerate(bboxes):
        emb = embeddings[i] if i < len(embeddings) else None

        if emb is None:
            faces.append({
                "box": bbox,
                "score_type": "cosine_similarity",
                "score": None,
                "distance": None,
                "matched": False,
                "status": "detected_only",
                "label": "Face Detected | Recognition Unavailable",
                "person": None,
            })
            continue

        if not has_enrolled:
            faces.append({
                "box": bbox,
                "score_type": "cosine_similarity",
                "score": None,
                "distance": None,
                "matched": False,
                "status": "no_enrolled",
                "label": "No enrolled profiles",
                "person": None,
            })
            continue

        # Search pgvector
        search_res = search_face(emb, db)
        sim = search_res.get("confidence")
        dist = search_res.get("distance")
        matched = search_res.get("matched", False)
        result_code = search_res.get("result", "no_match")

        if matched:
            status = "matched"
            person_name = search_res.get("person_name") or "Authorized Person"
            score_str = f"{sim:.2f}" if sim is not None else "N/A"
            label = f"Known: {person_name} | Similarity: {score_str}"
            person = {
                "id": str(search_res["person_id"]),
                "name": person_name,
                "person_type": search_res.get("candidates", [{}])[0].get("person_type") if search_res.get("candidates") else None,
                "department": None,
            }
        elif result_code == "low_confidence":
            status = "low_confidence"
            score_str = f"{sim:.2f}" if sim is not None else "0.00"
            label = f"Unknown | Best Similarity: {score_str}"
            person = None
            matched = False
        else:
            status = "unknown"
            score_str = f"{sim:.2f}" if sim is not None else "0.00"
            label = f"Unknown | Best Similarity: {score_str}"
            person = None
            matched = False

        faces.append({
            "box": bbox,
            "score_type": "cosine_similarity",
            "score": round(sim, 4) if sim is not None else None,
            "distance": round(dist, 4) if dist is not None else None,
            "matched": matched,
            "status": status,
            "label": label,
            "person": person,
        })

    return faces, None

