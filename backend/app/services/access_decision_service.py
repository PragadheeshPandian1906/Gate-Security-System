"""
SmartGuard AI — Access Decision Engine (Phase 3)

Evaluates a submitted access attempt using exclusively server-side
trusted data. The engine:
  1. Validates the face verification result against the persisted record.
  2. Validates the plate/vehicle against the persisted ALPR record.
  3. Re-fetches person and vehicle from the database (never trusts client IDs).
  4. Evaluates watchlist, ownership, person/vehicle status, and schedule.
  5. Applies the decision table in documented precedence order.
  6. Persists the access attempt and triggers gate simulation.

DECISION PRECEDENCE (fail-closed at every step):
  1. DB/service unavailable             → DENY  (DATABASE_UNAVAILABLE)
  2. Face engine unavailable / error    → MANUAL_REVIEW (FACE_ENGINE_UNAVAILABLE)
  3. No face detected                   → DENY  (FACE_NOT_DETECTED)
  4. Multiple faces (ambiguous)         → MANUAL_REVIEW (FACE_AMBIGUOUS)
  5. Face unknown / low confidence      → DENY  (FACE_UNKNOWN)
  6. Plate not detected                 → DENY  (PLATE_NOT_DETECTED)
  7. Plate unreadable                   → DENY  (PLATE_UNREADABLE)
  8. Vehicle not registered             → DENY  (VEHICLE_NOT_REGISTERED)
  9. High-severity watchlist entry      → DENY  (WATCHLIST_BLOCK)
 10. Other active watchlist entry       → MANUAL_REVIEW (WATCHLIST_REVIEW)
 11. Vehicle flagged                    → DENY  (VEHICLE_FLAGGED)
 12. Vehicle inactive                   → DENY  (VEHICLE_INACTIVE)
 13. Person inactive / suspended        → DENY  (PERSON_INACTIVE / PERSON_SUSPENDED)
 14. Owner mismatch                     → MANUAL_REVIEW (OWNER_MISMATCH)
 15. Outside permitted schedule         → MANUAL_REVIEW (OUTSIDE_SCHEDULE)
 16. Schedule unavailable               → MANUAL_REVIEW (SCHEDULE_UNAVAILABLE)
 17. All checks pass                    → ALLOW (ALL_CHECKS_PASSED)

An unresolved check never defaults to ALLOW.
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("smartguard.access_decision")

# Validity window: a face_verification_id must have been created within this many
# seconds of the access attempt to be accepted as "fresh".
VERIFICATION_MAX_AGE_SECONDS = 120  # 2 minutes


def _get_face_verification(db, face_verification_id: Optional[str]) -> Optional[dict]:
    """
    Load and validate a face verification record from the database.
    Returns None if not found or too old.
    """
    if not face_verification_id:
        return None
    try:
        fv_uuid = uuid.UUID(face_verification_id)
    except ValueError:
        return None

    try:
        from sqlalchemy import select
        from app.models.people import FaceVerification

        fv = db.execute(
            select(FaceVerification).where(FaceVerification.id == fv_uuid)
        ).scalar_one_or_none()
        if fv is None:
            return None

        # Check freshness
        now = datetime.now(timezone.utc)
        ts = fv.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        if age > VERIFICATION_MAX_AGE_SECONDS:
            logger.warning(
                "access Face verification %s is %.0fs old (max=%ds) — rejecting",
                face_verification_id, age, VERIFICATION_MAX_AGE_SECONDS,
            )
            return None

        return {
            "id": str(fv.id),
            "result": fv.result,
            "confidence": fv.confidence,
            "distance": fv.distance,
            "matched_person_id": str(fv.matched_person_id) if fv.matched_person_id else None,
            "faces_detected": fv.faces_detected,
        }
    except Exception as exc:
        logger.error("access Failed to load face verification: %s", exc)
        return None


def _get_alpr_verification(db, alpr_verification_id: Optional[str]) -> Optional[dict]:
    """
    Load and validate an ALPR verification record from the database.
    Returns None if not found or too old.
    """
    if not alpr_verification_id:
        return None
    try:
        av_uuid = uuid.UUID(alpr_verification_id)
    except ValueError:
        return None

    try:
        from sqlalchemy import select
        from app.models.people import AlprVerification

        av = db.execute(
            select(AlprVerification).where(AlprVerification.id == av_uuid)
        ).scalar_one_or_none()
        if av is None:
            return None

        now = datetime.now(timezone.utc)
        ts = av.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        if age > VERIFICATION_MAX_AGE_SECONDS:
            logger.warning(
                "access ALPR verification %s is %.0fs old (max=%ds) — rejecting",
                alpr_verification_id, age, VERIFICATION_MAX_AGE_SECONDS,
            )
            return None

        return {
            "id": str(av.id),
            "result": av.result,
            "detected_plate": av.detected_plate,
            "detected_plate_normalized": av.detected_plate_normalized,
            "detection_confidence": av.detection_confidence,
            "ocr_confidence": av.ocr_confidence,
            "matched_vehicle_id": str(av.matched_vehicle_id) if av.matched_vehicle_id else None,
        }
    except Exception as exc:
        logger.error("access Failed to load ALPR verification: %s", exc)
        return None


def _get_person(db, person_id: str) -> Optional[dict]:
    """Load a campus person from the database."""
    try:
        pid = uuid.UUID(person_id)
        from sqlalchemy import select
        from app.models.people import CampusPerson
        person = db.execute(
            select(CampusPerson).where(CampusPerson.id == pid)
        ).scalar_one_or_none()
        if person is None:
            return None
        return {
            "id": str(person.id),
            "full_name": person.full_name,
            "status": person.status,
            "person_type": person.person_type,
        }
    except Exception as exc:
        logger.error("access Failed to load person %s: %s", person_id, exc)
        return None


def _get_vehicle(db, vehicle_id: str) -> Optional[dict]:
    """Load a vehicle from the database."""
    try:
        vid = uuid.UUID(vehicle_id)
        from sqlalchemy import select
        from app.models.people import Vehicle
        vehicle = db.execute(
            select(Vehicle).where(Vehicle.id == vid)
        ).scalar_one_or_none()
        if vehicle is None:
            return None
        return {
            "id": str(vehicle.id),
            "plate_number": vehicle.plate_number,
            "plate_normalized": vehicle.plate_normalized,
            "status": vehicle.status,
            "owner_person_id": str(vehicle.owner_person_id) if vehicle.owner_person_id else None,
            "owner_name": vehicle.owner_name,
        }
    except Exception as exc:
        logger.error("access Failed to load vehicle %s: %s", vehicle_id, exc)
        return None


def _persist_attempt(db, attempt_data: dict) -> str:
    """Persist the access attempt to the database. Returns the attempt ID."""
    from sqlalchemy import text as sqla_text
    attempt_id = str(uuid.uuid4())
    try:
        db.execute(
            sqla_text("""
                INSERT INTO access_attempts (
                    id, timestamp, direction,
                    face_verification_id, face_result, face_confidence,
                    matched_person_id, person_status,
                    alpr_verification_id, detected_plate, detected_plate_normalized,
                    matched_vehicle_id, vehicle_status, vehicle_owner_person_id,
                    ownership_ok, schedule_ok, watchlist_hit, watchlist_severity,
                    decision, reason_codes, reason_text, gate_result,
                    processing_ms, initiated_by,
                    review_required, review_resolved
                ) VALUES (
                    :id, now(), :direction,
                    :face_ver_id, :face_result, :face_confidence,
                    :person_id, :person_status,
                    :alpr_ver_id, :plate, :plate_norm,
                    :vehicle_id, :vehicle_status, :vehicle_owner_id,
                    :ownership_ok, :schedule_ok, :watchlist_hit, :watchlist_severity,
                    :decision, CAST(:reason_codes AS json), :reason_text, :gate_result,
                    :processing_ms, :initiated_by,
                    :review_required, false
                )
            """),
            {
                "id": attempt_id,
                "direction": attempt_data.get("direction"),
                "face_ver_id": attempt_data.get("face_verification_id"),
                "face_result": attempt_data.get("face_result"),
                "face_confidence": attempt_data.get("face_confidence"),
                "person_id": attempt_data.get("matched_person_id"),
                "person_status": attempt_data.get("person_status"),
                "alpr_ver_id": attempt_data.get("alpr_verification_id"),
                "plate": attempt_data.get("detected_plate"),
                "plate_norm": attempt_data.get("detected_plate_normalized"),
                "vehicle_id": attempt_data.get("matched_vehicle_id"),
                "vehicle_status": attempt_data.get("vehicle_status"),
                "vehicle_owner_id": attempt_data.get("vehicle_owner_person_id"),
                "ownership_ok": attempt_data.get("ownership_ok"),
                "schedule_ok": attempt_data.get("schedule_ok"),
                "watchlist_hit": attempt_data.get("watchlist_hit"),
                "watchlist_severity": attempt_data.get("watchlist_severity"),
                "decision": attempt_data.get("decision"),
                "reason_codes": str(attempt_data.get("reason_codes", [])).replace("'", '"'),
                "reason_text": attempt_data.get("reason_text"),
                "gate_result": attempt_data.get("gate_result", "CLOSED"),
                "processing_ms": attempt_data.get("processing_ms"),
                "initiated_by": attempt_data.get("initiated_by"),
                "review_required": attempt_data.get("decision") == "MANUAL_REVIEW",
            },
        )
        db.commit()
    except Exception as exc:
        logger.error("access Failed to persist attempt: %s", exc, exc_info=True)
        db.rollback()
    return attempt_id


def evaluate_access_attempt(
    db,
    direction: str,
    face_verification_id: Optional[str],
    alpr_verification_id: Optional[str],
    initiated_by: Optional[str],
) -> dict:
    """
    Main entry point for the access-decision engine.

    Args:
        db                    : SQLAlchemy session
        direction             : 'ENTRY' | 'EXIT'
        face_verification_id  : ID of a recent face_verifications row
        alpr_verification_id  : ID of a recent alpr_verifications row
        initiated_by          : security_accounts.id of the requesting officer

    Returns the complete decision record dict.
    """
    t_start = time.perf_counter()
    reason_codes: list[str] = []
    decision = "DENY"
    gate_result = "CLOSED"

    # ── Collected context (populated below) ────────────────────────────────
    face_ver = None
    alpr_ver = None
    person = None
    vehicle = None
    ownership_ok = None
    schedule_result = None
    watchlist_result = None

    # ── 1. Load and validate face verification ──────────────────────────────
    try:
        face_ver = _get_face_verification(db, face_verification_id)
    except Exception as exc:
        logger.error("access DB error loading face verification: %s", exc)
        reason_codes.append("DATABASE_UNAVAILABLE")
        decision = "DENY"
        gate_result = "CLOSED"
        return _build_result(
            db, t_start, direction, face_ver, alpr_ver, person, vehicle,
            ownership_ok, schedule_result, watchlist_result,
            decision, reason_codes, gate_result, initiated_by,
        )

    if face_ver is None:
        # Could be: verification not found, too old, or invalid ID
        reason_codes.append("VERIFICATION_INCOMPLETE")
        decision = "DENY"
        return _build_result(
            db, t_start, direction, face_ver, alpr_ver, person, vehicle,
            ownership_ok, schedule_result, watchlist_result,
            decision, reason_codes, gate_result, initiated_by,
        )

    # Check face result
    faces_detected = face_ver.get("faces_detected", 0)
    face_result = face_ver.get("result", "error")

    if face_result == "error":
        reason_codes.append("FACE_ENGINE_UNAVAILABLE")
        decision = "MANUAL_REVIEW"
        gate_result = "MANUAL_REVIEW"
    elif faces_detected == 0 or face_result == "no_face":
        reason_codes.append("FACE_NOT_DETECTED")
        decision = "DENY"
    elif faces_detected > 1:
        reason_codes.append("FACE_AMBIGUOUS")
        decision = "MANUAL_REVIEW"
        gate_result = "MANUAL_REVIEW"
    elif face_result in ("no_match", "low_confidence"):
        reason_codes.append("FACE_UNKNOWN")
        decision = "DENY"
    elif face_result != "matched":
        reason_codes.append("FACE_UNKNOWN")
        decision = "DENY"

    # If face is not matched, we can still continue to collect plate info
    # but the final decision cannot be ALLOW without a matched face.
    face_ok = face_result == "matched" and "FACE_ENGINE_UNAVAILABLE" not in reason_codes

    # ── 2. Load person from DB (never trust client-supplied identity) ───────
    if face_ok and face_ver.get("matched_person_id"):
        person = _get_person(db, face_ver["matched_person_id"])
        if person is None:
            reason_codes.append("VERIFICATION_INCOMPLETE")
            face_ok = False
            decision = "DENY"

    # ── 3. Load and validate ALPR verification ──────────────────────────────
    try:
        alpr_ver = _get_alpr_verification(db, alpr_verification_id)
    except Exception as exc:
        logger.error("access DB error loading ALPR verification: %s", exc)
        if "DATABASE_UNAVAILABLE" not in reason_codes:
            reason_codes.append("DATABASE_UNAVAILABLE")
        decision = "DENY"
        return _build_result(
            db, t_start, direction, face_ver, alpr_ver, person, vehicle,
            ownership_ok, schedule_result, watchlist_result,
            decision, reason_codes, gate_result, initiated_by,
        )

    if alpr_ver is None:
        reason_codes.append("VERIFICATION_INCOMPLETE")
        decision = "DENY"
        return _build_result(
            db, t_start, direction, face_ver, alpr_ver, person, vehicle,
            ownership_ok, schedule_result, watchlist_result,
            decision, reason_codes, gate_result, initiated_by,
        )

    plate_result = alpr_ver.get("result", "error")
    plate_norm = alpr_ver.get("detected_plate_normalized")

    if plate_result == "no_plate":
        reason_codes.append("PLATE_NOT_DETECTED")
        if decision not in ("DENY",):
            decision = "DENY"
    elif plate_result == "error":
        reason_codes.append("PLATE_UNREADABLE")
        if decision not in ("DENY",):
            decision = "DENY"
    elif plate_result == "no_match" or not alpr_ver.get("matched_vehicle_id"):
        reason_codes.append("VEHICLE_NOT_REGISTERED")
        if decision not in ("DENY",):
            decision = "DENY"

    plate_ok = plate_result == "matched" and alpr_ver.get("matched_vehicle_id")

    # ── 4. Load vehicle from DB ─────────────────────────────────────────────
    if alpr_ver.get("matched_vehicle_id"):
        vehicle = _get_vehicle(db, alpr_ver["matched_vehicle_id"])
        if vehicle is None:
            reason_codes.append("VERIFICATION_INCOMPLETE")
            plate_ok = False
            if decision != "DENY":
                decision = "DENY"

    # ── 5. Watchlist check (uses both vehicle_id and normalized plate) ──────
    try:
        from app.services.watchlist_service import check_watchlist
        wl_vehicle_id = uuid.UUID(vehicle["id"]) if vehicle else None
        watchlist_result = check_watchlist(
            db,
            vehicle_id=wl_vehicle_id,
            plate_normalized=plate_norm,
        )
        if watchlist_result["hit"]:
            reason_codes.append(watchlist_result["reason_code"])
            if watchlist_result["reason_code"] == "WATCHLIST_BLOCK":
                decision = "DENY"
                gate_result = "CLOSED"
            else:  # WATCHLIST_REVIEW
                if decision not in ("DENY",):
                    decision = "MANUAL_REVIEW"
                    gate_result = "MANUAL_REVIEW"
    except Exception as exc:
        logger.error("access Watchlist check failed: %s", exc)
        reason_codes.append("WATCHLIST_REVIEW")
        if decision not in ("DENY",):
            decision = "MANUAL_REVIEW"
            gate_result = "MANUAL_REVIEW"
        watchlist_result = {"hit": True, "severity": None, "reason_code": "WATCHLIST_REVIEW",
                            "reason_text": str(exc), "entry_id": None, "entry_reason": None}

    # ── 6. Vehicle status check ─────────────────────────────────────────────
    if vehicle:
        if vehicle["status"] == "flagged":
            if "WATCHLIST_BLOCK" not in reason_codes and "VEHICLE_FLAGGED" not in reason_codes:
                reason_codes.append("VEHICLE_FLAGGED")
            if decision not in ("DENY",):
                decision = "DENY"
                gate_result = "CLOSED"
        elif vehicle["status"] == "inactive":
            reason_codes.append("VEHICLE_INACTIVE")
            if decision not in ("DENY",):
                decision = "DENY"
                gate_result = "CLOSED"

    # ── 7. Person status check ──────────────────────────────────────────────
    if person:
        if person["status"] == "inactive":
            reason_codes.append("PERSON_INACTIVE")
            if decision not in ("DENY",):
                decision = "DENY"
                gate_result = "CLOSED"
        elif person["status"] == "suspended":
            reason_codes.append("PERSON_SUSPENDED")
            if decision not in ("DENY",):
                decision = "DENY"
                gate_result = "CLOSED"

    # ── 8. Ownership validation ─────────────────────────────────────────────
    if person and vehicle:
        vehicle_owner_id = vehicle.get("owner_person_id")
        if not vehicle_owner_id:
            reason_codes.append("OWNER_MISMATCH")
            ownership_ok = False
            if decision not in ("DENY",):
                decision = "MANUAL_REVIEW"
                gate_result = "MANUAL_REVIEW"
        elif vehicle_owner_id != person["id"]:
            reason_codes.append("OWNER_MISMATCH")
            ownership_ok = False
            if decision not in ("DENY",):
                decision = "MANUAL_REVIEW"
                gate_result = "MANUAL_REVIEW"
        else:
            ownership_ok = True

    # ── 9. Schedule check ───────────────────────────────────────────────────
    # Only check schedule if we haven't already denied for a hard reason
    if decision != "DENY" or "WATCHLIST_BLOCK" not in reason_codes:
        try:
            from app.services.schedule_service import evaluate_schedule
            schedule_result = evaluate_schedule(db)
            if not schedule_result["ok"]:
                sc = schedule_result["reason_code"]
                reason_codes.append(sc)
                if decision not in ("DENY",):
                    decision = "MANUAL_REVIEW"
                    gate_result = "MANUAL_REVIEW"
        except Exception as exc:
            logger.error("access Schedule check failed: %s", exc)
            reason_codes.append("SCHEDULE_UNAVAILABLE")
            if decision not in ("DENY",):
                decision = "MANUAL_REVIEW"
                gate_result = "MANUAL_REVIEW"
            schedule_result = {
                "ok": False, "reason_code": "SCHEDULE_UNAVAILABLE",
                "detail": str(exc), "campus_timezone": "Asia/Kolkata",
                "weekday": "", "evaluated_local": "",
                "schedule_open_time": None, "schedule_close_time": None,
            }

    # ── 10. Strict Precedence Order Evaluation ──────────────────────────────
    HARD_DENY_CODES = {
        "DATABASE_UNAVAILABLE",
        "VERIFICATION_INCOMPLETE",
        "FACE_NOT_DETECTED",
        "FACE_UNKNOWN",
        "PLATE_NOT_DETECTED",
        "PLATE_UNREADABLE",
        "VEHICLE_NOT_REGISTERED",
        "WATCHLIST_BLOCK",
        "VEHICLE_FLAGGED",
        "VEHICLE_INACTIVE",
        "PERSON_INACTIVE",
        "PERSON_SUSPENDED",
    }

    MANUAL_REVIEW_CODES = {
        "FACE_ENGINE_UNAVAILABLE",
        "FACE_AMBIGUOUS",
        "WATCHLIST_REVIEW",
        "OWNER_MISMATCH",
        "OUTSIDE_SCHEDULE",
        "SCHEDULE_UNAVAILABLE",
    }

    if any(code in HARD_DENY_CODES for code in reason_codes) or not face_ok or not plate_ok:
        decision = "DENY"
        gate_result = "CLOSED"
    elif any(code in MANUAL_REVIEW_CODES for code in reason_codes) or ownership_ok is False:
        decision = "MANUAL_REVIEW"
        gate_result = "MANUAL_REVIEW"
    elif not reason_codes and ownership_ok is True and face_ok and plate_ok:
        decision = "ALLOW"
        gate_result = "OPEN"
        reason_codes.append("ALL_CHECKS_PASSED")
    else:
        decision = "DENY"
        gate_result = "CLOSED"
        if not reason_codes:
            reason_codes.append("VERIFICATION_INCOMPLETE")

    return _build_result(
        db, t_start, direction, face_ver, alpr_ver, person, vehicle,
        ownership_ok, schedule_result, watchlist_result,
        decision, reason_codes, gate_result, initiated_by,
    )


def _build_result(
    db,
    t_start: float,
    direction: str,
    face_ver: Optional[dict],
    alpr_ver: Optional[dict],
    person: Optional[dict],
    vehicle: Optional[dict],
    ownership_ok: Optional[bool],
    schedule_result: Optional[dict],
    watchlist_result: Optional[dict],
    decision: str,
    reason_codes: list[str],
    gate_result: str,
    initiated_by: Optional[str],
) -> dict:
    """Assemble the final result dict, trigger gate, and persist the attempt."""
    processing_ms = (time.perf_counter() - t_start) * 1000.0

    # Apply gate transition
    attempt_id_placeholder = str(uuid.uuid4())
    from app.services import gate_service
    gate_service.apply_decision(decision, direction, attempt_id_placeholder)
    # If MANUAL_REVIEW, gate state is MANUAL_REVIEW; align gate_result
    if decision == "MANUAL_REVIEW":
        gate_result = "MANUAL_REVIEW"
    elif decision == "ALLOW":
        gate_result = "OPEN"
    else:
        gate_result = "CLOSED"

    # Build human-readable reason
    reason_text = _build_reason_text(
        decision, reason_codes, direction, person, vehicle,
        schedule_result, watchlist_result, ownership_ok,
    )

    attempt_data = {
        "direction": direction,
        "face_verification_id": face_ver["id"] if face_ver else None,
        "face_result": face_ver.get("result") if face_ver else None,
        "face_confidence": face_ver.get("confidence") if face_ver else None,
        "matched_person_id": person["id"] if person else None,
        "person_status": person.get("status") if person else None,
        "alpr_verification_id": alpr_ver["id"] if alpr_ver else None,
        "detected_plate": alpr_ver.get("detected_plate") if alpr_ver else None,
        "detected_plate_normalized": alpr_ver.get("detected_plate_normalized") if alpr_ver else None,
        "matched_vehicle_id": vehicle["id"] if vehicle else None,
        "vehicle_status": vehicle.get("status") if vehicle else None,
        "vehicle_owner_person_id": vehicle.get("owner_person_id") if vehicle else None,
        "ownership_ok": ownership_ok,
        "schedule_ok": schedule_result.get("ok") if schedule_result else None,
        "watchlist_hit": watchlist_result.get("hit") if watchlist_result else None,
        "watchlist_severity": watchlist_result.get("severity") if watchlist_result else None,
        "decision": decision,
        "reason_codes": reason_codes,
        "reason_text": reason_text,
        "gate_result": gate_result,
        "processing_ms": round(processing_ms, 2),
        "initiated_by": initiated_by,
    }

    attempt_id = _persist_attempt(db, attempt_data)
    # Update gate service with the real attempt_id
    from app.services import gate_service
    gate_service._last_attempt_id = attempt_id

    # ── Phase 4: Alert evaluation (never blocks the access decision) ──────
    try:
        from app.services import alert_service as _alert_svc
        alert_attempt_data = {
            **attempt_data,
            "decision": decision,
            "reason_codes": reason_codes,
            "detected_plate": alpr_ver.get("detected_plate") if alpr_ver else None,
            "detected_plate_normalized": alpr_ver.get("detected_plate_normalized") if alpr_ver else None,
            "matched_person_id": person["id"] if person else None,
            "matched_vehicle_id": vehicle["id"] if vehicle else None,
            "watchlist_hit": watchlist_result.get("hit") if watchlist_result else False,
            "watchlist_severity": watchlist_result.get("severity") if watchlist_result else None,
            "direction": direction,
            "reason_text": None,  # will be set below
        }
        # Provide reason_text via the attempt_data dict already built above
        alert_attempt_data["reason_text"] = attempt_data.get("reason_text")
        _alert_svc.evaluate_and_create_alert(db, attempt_id, alert_attempt_data)
    except Exception as _ae:
        logger.error("access_decision Alert service evaluation failed: %s", _ae)

    # ── Phase 4: Queue email notification asynchronously ──────────────────
    try:
        from app.services import notification_service as _notif_svc
        _notif_svc.queue_alert_notifications_after_commit(db, attempt_id, attempt_data, decision)
    except Exception as _ne:
        logger.error("access_decision Notification queue failed: %s", _ne)

    return {
        "attempt_id": attempt_id,
        "direction": direction,
        "decision": decision,
        "gate_result": gate_result,
        "reason_codes": reason_codes,
        "reason_text": reason_text,
        "face": {
            "result": face_ver.get("result") if face_ver else None,
            "confidence": face_ver.get("confidence") if face_ver else None,
            "matched_person": person,
        },
        "plate": {
            "detected_plate": alpr_ver.get("detected_plate") if alpr_ver else None,
            "detected_plate_normalized": alpr_ver.get("detected_plate_normalized") if alpr_ver else None,
            "matched_vehicle": vehicle,
        },
        "ownership_ok": ownership_ok,
        "schedule": schedule_result,
        "watchlist": watchlist_result,
        "processing_ms": round(processing_ms, 2),
    }



def _build_reason_text(
    decision: str,
    reason_codes: list[str],
    direction: str,
    person: Optional[dict],
    vehicle: Optional[dict],
    schedule_result: Optional[dict],
    watchlist_result: Optional[dict],
    ownership_ok: Optional[bool],
) -> str:
    """Build a clear human-readable explanation for the decision."""
    parts = []

    direction_label = "ENTRY" if direction == "ENTRY" else "EXIT"

    if decision == "ALLOW":
        name = person["full_name"] if person else "Unknown"
        plate = vehicle["plate_number"] if vehicle else "Unknown"
        parts.append(f"{direction_label} ALLOWED: {name} driving {plate}.")
        parts.append("All checks passed: face matched, vehicle registered, ownership verified, schedule active, no watchlist restrictions.")
    elif decision == "MANUAL_REVIEW":
        parts.append(f"{direction_label} — MANUAL REVIEW REQUIRED.")
        if "FACE_ENGINE_UNAVAILABLE" in reason_codes:
            parts.append("Face recognition engine encountered an error.")
        if "FACE_AMBIGUOUS" in reason_codes:
            parts.append("Multiple faces detected in frame — identity is ambiguous.")
        if "OWNER_MISMATCH" in reason_codes:
            parts.append(
                f"Vehicle owner does not match identified person. "
                f"Vehicle owner: {vehicle.get('owner_name') or 'Not mapped'}."
            )
        if "OUTSIDE_SCHEDULE" in reason_codes and schedule_result:
            parts.append(schedule_result.get("detail", "Outside permitted access hours."))
        if "SCHEDULE_UNAVAILABLE" in reason_codes:
            parts.append("Access schedule is unavailable. Manual verification required.")
        if "WATCHLIST_REVIEW" in reason_codes and watchlist_result:
            parts.append(watchlist_result.get("reason_text", "Vehicle is on a watchlist."))
    else:  # DENY
        parts.append(f"{direction_label} DENIED.")
        if "DATABASE_UNAVAILABLE" in reason_codes:
            parts.append("Backend database unavailable. Fail-closed.")
        if "VERIFICATION_INCOMPLETE" in reason_codes:
            parts.append("Verification data is missing, expired (>2 min), or invalid.")
        if "FACE_NOT_DETECTED" in reason_codes:
            parts.append("No face detected in the verification frame.")
        if "FACE_UNKNOWN" in reason_codes:
            parts.append("Face not recognized or similarity below threshold.")
        if "PLATE_NOT_DETECTED" in reason_codes:
            parts.append("No license plate detected.")
        if "PLATE_UNREADABLE" in reason_codes:
            parts.append("License plate detected but OCR failed to read it.")
        if "VEHICLE_NOT_REGISTERED" in reason_codes:
            parts.append("License plate is not registered in the system.")
        if "WATCHLIST_BLOCK" in reason_codes and watchlist_result:
            parts.append(watchlist_result.get("reason_text", "Vehicle is on the high-severity watchlist."))
        if "VEHICLE_FLAGGED" in reason_codes:
            parts.append("Vehicle is flagged in the system.")
        if "VEHICLE_INACTIVE" in reason_codes:
            parts.append("Vehicle registration is inactive.")
        if "PERSON_INACTIVE" in reason_codes:
            parts.append("Person's campus access is currently inactive.")
        if "PERSON_SUSPENDED" in reason_codes:
            parts.append("Person's campus access is suspended.")

    return " ".join(parts)


def resolve_manual_review(
    db,
    attempt_id: str,
    resolution: str,   # 'approved' | 'denied'
    reason: str,
    reviewed_by: str,
) -> dict:
    """
    Resolve a pending manual-review attempt.
    Re-validates person/vehicle/watchlist state before accepting approval.

    Returns a dict with: success, message, new_gate_result
    """
    if resolution not in ("approved", "denied"):
        return {"success": False, "message": "Resolution must be 'approved' or 'denied'.", "new_gate_result": None}

    if not reason or not reason.strip():
        return {"success": False, "message": "A mandatory reason must be provided.", "new_gate_result": None}

    try:
        att_uuid = uuid.UUID(attempt_id)
    except ValueError:
        return {"success": False, "message": "Invalid attempt ID.", "new_gate_result": None}

    try:
        from sqlalchemy import select, text as sqla_text
        from app.models.access import AccessAttempt

        attempt = db.execute(
            select(AccessAttempt).where(AccessAttempt.id == att_uuid)
        ).scalar_one_or_none()

        if attempt is None:
            return {"success": False, "message": "Attempt not found.", "new_gate_result": None}

        if not attempt.review_required:
            return {"success": False, "message": "This attempt does not require manual review.", "new_gate_result": None}

        if attempt.review_resolved:
            return {"success": False, "message": "This attempt has already been resolved.", "new_gate_result": None}

        # Re-validate before approving
        if resolution == "approved":
            # Check watchlist again — a new entry may have been added since the original attempt
            from app.services.watchlist_service import check_watchlist
            veh_id = uuid.UUID(str(attempt.matched_vehicle_id)) if attempt.matched_vehicle_id else None
            wl = check_watchlist(db, vehicle_id=veh_id, plate_normalized=attempt.detected_plate_normalized)
            if wl["hit"] and wl["reason_code"] == "WATCHLIST_BLOCK":
                return {
                    "success": False,
                    "message": f"Cannot approve: vehicle is now on the high-severity watchlist. {wl['reason_text']}",
                    "new_gate_result": None,
                }

            # Check person and vehicle still eligible
            if attempt.matched_person_id:
                person = _get_person(db, str(attempt.matched_person_id))
                if person and person["status"] not in ("active",):
                    return {
                        "success": False,
                        "message": f"Cannot approve: person status is {person['status']}.",
                        "new_gate_result": None,
                    }

            if attempt.matched_vehicle_id:
                vehicle = _get_vehicle(db, str(attempt.matched_vehicle_id))
                if vehicle and vehicle["status"] == "inactive":
                    return {
                        "success": False,
                        "message": "Cannot approve: vehicle is inactive.",
                        "new_gate_result": None,
                    }

        new_gate = "OPEN" if resolution == "approved" else "CLOSED"

        db.execute(
            sqla_text("""
                UPDATE access_attempts SET
                    review_resolved = true,
                    review_resolution = :resolution,
                    review_reason = :reason,
                    reviewed_by = :reviewed_by,
                    reviewed_at = now(),
                    gate_result = :gate_result
                WHERE id = :id
            """),
            {
                "resolution": resolution,
                "reason": reason.strip(),
                "reviewed_by": reviewed_by,
                "gate_result": new_gate,
                "id": str(att_uuid),
            },
        )
        db.commit()

        # Apply gate if approved
        if resolution == "approved":
            from app.services import gate_service
            gate_service.apply_decision("ALLOW", str(attempt.direction), str(attempt_id))

        logger.info(
            "access Manual review resolved: attempt=%s resolution=%s reviewed_by=%s",
            attempt_id, resolution, reviewed_by,
        )
        return {
            "success": True,
            "message": f"Attempt {resolution} by officer.",
            "new_gate_result": new_gate,
        }

    except Exception as exc:
        logger.error("access resolve_manual_review failed: %s", exc, exc_info=True)
        db.rollback()
        return {"success": False, "message": f"Internal error: {exc}", "new_gate_result": None}
