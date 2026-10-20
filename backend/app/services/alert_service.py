"""
SmartGuard AI — Phase 4 Alert Service

Evaluates completed access attempts and creates/updates persistent security alerts.

Rules:
  - Alerts are generated from COMPLETED, PERSISTED access_attempt records only.
  - Never generate alerts from raw camera frames or transient in-memory state.
  - Deduplication key prevents creating multiple alerts for the same logical event.
  - Repeated-denial detection groups by normalized plate within a configurable window.
  - Alert severity follows watchlist_severity when a watchlist is involved.
  - Alert creation NEVER modifies the original access decision or gate state.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("smartguard.alert_service")

# ─── Configurable thresholds (could be moved to Settings later) ───────────────
REPEATED_DENIAL_THRESHOLD = 3          # number of denials within window
REPEATED_DENIAL_WINDOW_MINUTES = 10   # minutes
ALLOW_REPEATED_DENIAL_FOR_UNKNOWN = True  # group by plate even if person unknown

# Map watchlist severity → alert severity
_WL_SEVERITY_MAP = {
    "high": "CRITICAL",
    "medium": "HIGH",
    "low": "MEDIUM",
}


# ---------------------------------------------------------------------------
# Public entry point — called by access_decision_service after DB commit
# ---------------------------------------------------------------------------
def evaluate_and_create_alert(db, attempt_id: str, attempt_data: dict) -> Optional[str]:
    """
    Evaluate a just-persisted access attempt and create/update a security alert
    if the event meets configured rules.

    Parameters
    ----------
    db           : SQLAlchemy Session
    attempt_id   : str UUID of the persisted access_attempt row
    attempt_data : dict snapshot of the attempt (decision, reason_codes, watchlist, etc.)

    Returns
    -------
    str alert_id if an alert was created/updated, None otherwise.
    """
    try:
        decision = attempt_data.get("decision", "")
        reason_codes = attempt_data.get("reason_codes") or []
        watchlist_hit = attempt_data.get("watchlist_hit", False)
        watchlist_severity = attempt_data.get("watchlist_severity") or ""
        detected_plate_normalized = attempt_data.get("detected_plate_normalized")
        detected_plate = attempt_data.get("detected_plate")
        matched_person_id = attempt_data.get("matched_person_id")
        matched_vehicle_id = attempt_data.get("matched_vehicle_id")
        direction = attempt_data.get("direction", "")
        reason_text = attempt_data.get("reason_text", "")

        alert_id = None

        # Rule 1: Watchlist hit — highest priority
        if watchlist_hit and watchlist_severity:
            alert_id = _handle_watchlist_alert(
                db, attempt_id, detected_plate, detected_plate_normalized,
                matched_person_id, matched_vehicle_id, watchlist_severity,
                reason_text, direction, reason_codes,
            )

        # Rule 2: DENY — create/merge an alert
        elif decision == "DENY":
            alert_id = _handle_deny_alert(
                db, attempt_id, detected_plate, detected_plate_normalized,
                matched_person_id, matched_vehicle_id, reason_codes,
                reason_text, direction,
            )

        # Rule 3: MANUAL_REVIEW — create an alert for officer visibility
        elif decision == "MANUAL_REVIEW":
            alert_id = _handle_manual_review_alert(
                db, attempt_id, detected_plate, detected_plate_normalized,
                matched_person_id, matched_vehicle_id, reason_codes, reason_text,
            )

        # Rule 4: ALLOW — no alert (standard authorized entry)

        # Rule 5: Repeated-denial check (independent of above — may escalate)
        if decision == "DENY" and detected_plate_normalized:
            _check_and_create_repeated_denial_alert(
                db, attempt_id, detected_plate, detected_plate_normalized,
                matched_person_id, matched_vehicle_id, direction,
            )

        db.commit()
        return alert_id

    except Exception as exc:
        logger.error(
            "alert_service evaluate_and_create_alert failed for attempt=%s: %s",
            attempt_id, exc, exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        # CRITICAL: never raise — must never block the access-decision response
        return None


# ---------------------------------------------------------------------------
# Rule handlers
# ---------------------------------------------------------------------------
def _handle_watchlist_alert(
    db, attempt_id: str, detected_plate: Optional[str],
    plate_normalized: Optional[str], person_id: Optional[str],
    vehicle_id: Optional[str], watchlist_severity: str,
    reason_text: str, direction: str, reason_codes: list,
) -> Optional[str]:
    """Create or escalate a watchlist-hit alert."""
    severity = _WL_SEVERITY_MAP.get(watchlist_severity.lower(), "HIGH")
    dedup_key = _make_dedup_key("watchlist", plate_normalized or attempt_id)
    category = "WATCHLIST_HIT"
    title = (
        f"Watchlist hit — {severity} — plate {detected_plate or 'unknown'}"
        f" ({direction})"
    )
    description = reason_text or f"Vehicle on watchlist ({watchlist_severity} severity)."

    return _upsert_alert(
        db,
        attempt_id=attempt_id,
        category=category,
        severity=severity,
        title=title,
        description=description,
        dedup_key=dedup_key,
        person_id=person_id,
        vehicle_id=vehicle_id,
        detected_plate=detected_plate,
    )


def _handle_deny_alert(
    db, attempt_id: str, detected_plate: Optional[str],
    plate_normalized: Optional[str], person_id: Optional[str],
    vehicle_id: Optional[str], reason_codes: list,
    reason_text: str, direction: str,
) -> Optional[str]:
    """Create or update a DENY alert."""
    # Severity based on reason
    if any(c in reason_codes for c in ("PERSON_SUSPENDED", "WATCHLIST_BLOCK")):
        severity = "HIGH"
    elif any(c in reason_codes for c in ("VEHICLE_FLAGGED", "PERSON_INACTIVE", "VEHICLE_INACTIVE")):
        severity = "MEDIUM"
    else:
        severity = "LOW"

    dedup_key = _make_dedup_key("deny", plate_normalized or attempt_id)
    title = (
        f"Access denied — {', '.join(reason_codes[:2]) if reason_codes else 'policy'}"
        f" — plate {detected_plate or 'unknown'} ({direction})"
    )

    return _upsert_alert(
        db,
        attempt_id=attempt_id,
        category="DENIED_ACCESS",
        severity=severity,
        title=title,
        description=reason_text,
        dedup_key=dedup_key,
        person_id=person_id,
        vehicle_id=vehicle_id,
        detected_plate=detected_plate,
    )


def _handle_manual_review_alert(
    db, attempt_id: str, detected_plate: Optional[str],
    plate_normalized: Optional[str], person_id: Optional[str],
    vehicle_id: Optional[str], reason_codes: list, reason_text: str,
) -> Optional[str]:
    """Create a manual-review alert — one per attempt (no dedup across attempts)."""
    severity = "MEDIUM"
    if "WATCHLIST_REVIEW" in reason_codes:
        severity = "HIGH"

    # Unique per attempt — no dedup_key (each manual review is distinct)
    title = (
        f"Manual review required — plate {detected_plate or 'unknown'}"
    )
    return _upsert_alert(
        db,
        attempt_id=attempt_id,
        category="MANUAL_REVIEW",
        severity=severity,
        title=title,
        description=reason_text,
        dedup_key=None,   # intentionally no dedup — each attempt gets its own alert
        person_id=person_id,
        vehicle_id=vehicle_id,
        detected_plate=detected_plate,
    )


def _check_and_create_repeated_denial_alert(
    db, attempt_id: str, detected_plate: Optional[str],
    plate_normalized: str, person_id: Optional[str],
    vehicle_id: Optional[str], direction: str,
) -> None:
    """
    Count recent DENY attempts for the same normalized plate within the window.
    If threshold is reached, create/escalate a REPEATED_DENIAL alert.
    """
    try:
        from sqlalchemy import select, func as sqla_func
        from app.models.access import AccessAttempt

        window_start = datetime.now(timezone.utc) - timedelta(minutes=REPEATED_DENIAL_WINDOW_MINUTES)

        count = db.execute(
            select(sqla_func.count(AccessAttempt.id)).where(
                AccessAttempt.detected_plate_normalized == plate_normalized,
                AccessAttempt.decision == "DENY",
                AccessAttempt.timestamp >= window_start,
            )
        ).scalar() or 0

        if count < REPEATED_DENIAL_THRESHOLD:
            return

        logger.info(
            "alert_service Repeated denial detected: plate=%s count=%d window=%dmin",
            plate_normalized, count, REPEATED_DENIAL_WINDOW_MINUTES,
        )

        dedup_key = _make_dedup_key("repeated_denial_window", plate_normalized)
        title = (
            f"Repeated access denial — {count} denials in {REPEATED_DENIAL_WINDOW_MINUTES}min"
            f" — plate {detected_plate or plate_normalized}"
        )
        description = (
            f"Plate {detected_plate or plate_normalized} has been denied {count} times "
            f"within the last {REPEATED_DENIAL_WINDOW_MINUTES} minutes ({direction})."
        )

        _upsert_alert(
            db,
            attempt_id=attempt_id,
            category="REPEATED_DENIAL",
            severity="HIGH",
            title=title,
            description=description,
            dedup_key=dedup_key,
            person_id=person_id,
            vehicle_id=vehicle_id,
            detected_plate=detected_plate,
        )

    except Exception as exc:
        logger.error("alert_service _check_repeated_denial failed: %s", exc)


# ---------------------------------------------------------------------------
# Core upsert — idempotent alert creation/escalation
# ---------------------------------------------------------------------------
def _upsert_alert(
    db,
    attempt_id: str,
    category: str,
    severity: str,
    title: str,
    description: Optional[str],
    dedup_key: Optional[str],
    person_id: Optional[str],
    vehicle_id: Optional[str],
    detected_plate: Optional[str],
) -> str:
    """
    Create a new alert or increment occurrence_count on an existing open alert
    with the same dedup_key.  Returns the alert UUID string.
    """
    from sqlalchemy import select, text as sqla_text
    from app.models.alerts import SecurityAlert, AlertNote

    existing = None
    if dedup_key:
        existing = db.execute(
            select(SecurityAlert).where(
                SecurityAlert.dedup_key == dedup_key,
                SecurityAlert.status.not_in(["RESOLVED", "DISMISSED"]),
            )
        ).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing:
        # Escalate severity if the new event is more severe
        sev_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if sev_order.get(severity, 0) > sev_order.get(existing.severity, 0):
            existing.severity = severity
            existing.title = title

        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.last_updated_at = now
        existing.description = description  # update with latest

        # Append attempt to related_attempt_ids
        ids = list(existing.related_attempt_ids or [])
        if attempt_id not in ids:
            ids.append(attempt_id)
        existing.related_attempt_ids = ids

        db.add(existing)
        alert_id = str(existing.id)
        logger.info("alert_service Updated alert id=%s occurrences=%d", alert_id, existing.occurrence_count)
    else:
        new_alert = SecurityAlert(
            id=uuid.uuid4(),
            category=category,
            severity=severity,
            title=title,
            description=description,
            status="OPEN",
            access_attempt_id=uuid.UUID(attempt_id) if attempt_id else None,
            person_id=uuid.UUID(person_id) if person_id else None,
            vehicle_id=uuid.UUID(vehicle_id) if vehicle_id else None,
            detected_plate=detected_plate,
            dedup_key=dedup_key,
            first_detected_at=now,
            last_updated_at=now,
            occurrence_count=1,
            related_attempt_ids=[attempt_id] if attempt_id else [],
        )
        db.add(new_alert)
        db.flush()  # get id before notes
        alert_id = str(new_alert.id)

        # System note
        note = AlertNote(
            id=uuid.uuid4(),
            alert_id=new_alert.id,
            author_id=None,
            note_type="SYSTEM",
            body=f"Alert automatically generated from access attempt {attempt_id}.",
            created_at=now,
        )
        db.add(note)
        logger.info(
            "alert_service Created alert id=%s category=%s severity=%s",
            alert_id, category, severity,
        )

    return alert_id


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------
def acknowledge_alert(db, alert_id: str, officer_id: str) -> dict:
    """Transition OPEN → ACKNOWLEDGED."""
    return _transition_alert(
        db, alert_id, officer_id,
        allowed_from=("OPEN",),
        new_status="ACKNOWLEDGED",
        note_body="Alert acknowledged by officer.",
        ack=True,
    )


def start_investigation(db, alert_id: str, officer_id: str) -> dict:
    """Transition OPEN | ACKNOWLEDGED → INVESTIGATING."""
    return _transition_alert(
        db, alert_id, officer_id,
        allowed_from=("OPEN", "ACKNOWLEDGED"),
        new_status="INVESTIGATING",
        note_body="Investigation started by officer.",
    )


def add_investigation_note(db, alert_id: str, officer_id: str, note_body: str) -> dict:
    """Add a free-text note to an alert in any non-terminal state."""
    from sqlalchemy import select
    from app.models.alerts import SecurityAlert, AlertNote
    try:
        alert = _get_alert_or_raise(db, alert_id)
        if alert["status"] in ("RESOLVED", "DISMISSED"):
            return {"success": False, "message": "Cannot add notes to a resolved/dismissed alert."}
        note = AlertNote(
            id=uuid.uuid4(),
            alert_id=uuid.UUID(alert_id),
            author_id=uuid.UUID(officer_id),
            note_type="NOTE",
            body=note_body.strip(),
        )
        db.add(note)
        db.commit()
        return {"success": True, "message": "Note added."}
    except LookupError as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:
        logger.error("alert_service add_note failed: %s", exc)
        db.rollback()
        return {"success": False, "message": "Internal error."}


def resolve_alert(db, alert_id: str, officer_id: str, resolution_reason: str) -> dict:
    """Transition any non-terminal state → RESOLVED."""
    if not resolution_reason or not resolution_reason.strip():
        return {"success": False, "message": "A resolution reason is required."}
    return _transition_alert(
        db, alert_id, officer_id,
        allowed_from=("OPEN", "ACKNOWLEDGED", "INVESTIGATING"),
        new_status="RESOLVED",
        note_body=f"Alert resolved: {resolution_reason.strip()}",
        resolve=True,
        resolution_reason=resolution_reason.strip(),
    )


def dismiss_alert(db, alert_id: str, officer_id: str, reason: Optional[str] = None) -> dict:
    """ADMIN-only: Transition → DISMISSED."""
    return _transition_alert(
        db, alert_id, officer_id,
        allowed_from=("OPEN", "ACKNOWLEDGED", "INVESTIGATING"),
        new_status="DISMISSED",
        note_body=f"Alert dismissed. {reason or ''}".strip(),
    )


def _transition_alert(
    db, alert_id: str, officer_id: str,
    allowed_from: tuple,
    new_status: str,
    note_body: str,
    ack: bool = False,
    resolve: bool = False,
    resolution_reason: Optional[str] = None,
) -> dict:
    from app.models.alerts import SecurityAlert, AlertNote
    from sqlalchemy import select
    try:
        alert_row = db.execute(
            select(SecurityAlert).where(SecurityAlert.id == uuid.UUID(alert_id))
        ).scalar_one_or_none()

        if alert_row is None:
            return {"success": False, "message": "Alert not found."}

        if alert_row.status not in allowed_from:
            return {
                "success": False,
                "message": f"Cannot transition from {alert_row.status} to {new_status}.",
            }

        now = datetime.now(timezone.utc)
        alert_row.status = new_status
        alert_row.last_updated_at = now

        if ack:
            alert_row.acknowledged_by = uuid.UUID(officer_id)
            alert_row.acknowledged_at = now

        if resolve:
            alert_row.resolved_by = uuid.UUID(officer_id)
            alert_row.resolved_at = now
            alert_row.resolution_reason = resolution_reason

        note = AlertNote(
            id=uuid.uuid4(),
            alert_id=uuid.UUID(alert_id),
            author_id=uuid.UUID(officer_id),
            note_type="STATUS_CHANGE",
            body=note_body,
            created_at=now,
        )
        db.add(note)
        db.add(alert_row)
        db.commit()
        return {"success": True, "message": f"Alert {new_status.lower()}."}

    except ValueError:
        return {"success": False, "message": "Invalid alert ID."}
    except Exception as exc:
        logger.error("alert_service _transition_alert failed: %s", exc)
        db.rollback()
        return {"success": False, "message": "Internal error."}


# ---------------------------------------------------------------------------
# Metrics for dashboard widgets
# ---------------------------------------------------------------------------
def get_alert_metrics(db) -> dict:
    """Return aggregated alert counts for dashboard display."""
    from sqlalchemy import select, func as sqla_func
    from app.models.alerts import SecurityAlert
    try:
        rows = db.execute(
            select(SecurityAlert.status, sqla_func.count(SecurityAlert.id))
            .group_by(SecurityAlert.status)
        ).all()
        counts = {r[0]: r[1] for r in rows}

        crit_high = db.execute(
            select(sqla_func.count(SecurityAlert.id)).where(
                SecurityAlert.severity.in_(["HIGH", "CRITICAL"]),
                SecurityAlert.status.not_in(["RESOLVED", "DISMISSED"]),
            )
        ).scalar() or 0

        return {
            "open": counts.get("OPEN", 0),
            "acknowledged": counts.get("ACKNOWLEDGED", 0),
            "investigating": counts.get("INVESTIGATING", 0),
            "resolved": counts.get("RESOLVED", 0),
            "dismissed": counts.get("DISMISSED", 0),
            "critical_high_unresolved": crit_high,
            "total_unresolved": (
                counts.get("OPEN", 0)
                + counts.get("ACKNOWLEDGED", 0)
                + counts.get("INVESTIGATING", 0)
            ),
        }
    except Exception as exc:
        logger.error("alert_service get_alert_metrics failed: %s", exc)
        return {
            "open": 0, "acknowledged": 0, "investigating": 0,
            "resolved": 0, "dismissed": 0, "critical_high_unresolved": 0,
            "total_unresolved": 0,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_dedup_key(prefix: str, identifier: str) -> str:
    """Create a short, stable deduplication key."""
    raw = f"{prefix}:{identifier}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _get_alert_or_raise(db, alert_id: str) -> dict:
    from sqlalchemy import select
    from app.models.alerts import SecurityAlert
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise LookupError("Invalid alert ID format.")
    row = db.execute(select(SecurityAlert).where(SecurityAlert.id == uid)).scalar_one_or_none()
    if row is None:
        raise LookupError("Alert not found.")
    return {"id": str(row.id), "status": row.status}
