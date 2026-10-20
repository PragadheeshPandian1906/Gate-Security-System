"""
SmartGuard AI — Simulated Gate Service (Phase 3)

Manages the simulated gate state machine.
This is a SOFTWARE SIMULATION ONLY — no physical hardware is connected.

Gate states:
  CLOSED       : Default/safe state. Barrier is down.
  OPEN         : Briefly open after an ALLOW decision (auto-closes).
  MANUAL_REVIEW: Pending human review; barrier stays down.

State is held in-process (single backend instance).
The gate starts in CLOSED state on every application startup.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger("smartguard.gate")

GateState = Literal["CLOSED", "OPEN", "MANUAL_REVIEW", "MANUAL_LATCHED_OPEN"]

# Default auto-close duration in seconds after an ALLOW decision
DEFAULT_OPEN_DURATION_SECONDS = 15.0

# ── In-process gate state ────────────────────────────────────────────────────
_state: GateState = "CLOSED"
_last_decision: str | None = None
_last_direction: str | None = None
_last_attempt_id: str | None = None
_last_transition_at: datetime | None = None
_auto_close_timer: threading.Timer | None = None
_gate_generation = 0
_manual_latched_at: datetime | None = None
_lock = threading.Lock()


def _cancel_timer() -> None:
    """Cancel any pending auto-close timer."""
    global _auto_close_timer
    if _auto_close_timer is not None:
        _auto_close_timer.cancel()
        _auto_close_timer = None


def _auto_close_callback(generation: int) -> None:
    """Called by the timer thread to return gate to CLOSED."""
    global _state, _last_transition_at, _auto_close_timer
    with _lock:
        if _state == "OPEN" and generation == _gate_generation:
            _state = "CLOSED"
            _last_transition_at = datetime.now(timezone.utc)
            _auto_close_timer = None
            logger.info("gate Auto-closed after open duration")


def get_status() -> dict:
    """Return simulated state and the IoT microservice controller snapshot."""
    from app.services.iot_service import iot_manager

    with _lock:
        return {
            "state": _state,
            "last_decision": _last_decision,
            "last_direction": _last_direction,
            "last_attempt_id": _last_attempt_id,
            "last_transition_at": _last_transition_at.isoformat() if _last_transition_at else None,
            "simulation_note": "SOFTWARE SIMULATION ONLY — no physical barrier is connected.",
            "iot_controller": iot_manager.get_status(),
        }


def apply_decision(
    decision: str,
    direction: str,
    attempt_id: str,
    open_duration_seconds: float = DEFAULT_OPEN_DURATION_SECONDS,
    dispatch_hardware: bool = True,
) -> GateState:
    """
    Apply an access decision to the gate state machine.

    - ALLOW       → OPEN (then auto-close after open_duration_seconds) & command ESP32
    - DENY        → CLOSED & update ESP32 LCD
    - MANUAL_REVIEW → MANUAL_REVIEW (stays until resolved or reset) & update ESP32 LCD

    Returns the new gate state.
    """
    global _state, _last_decision, _last_direction, _last_attempt_id
    global _last_transition_at, _auto_close_timer, _gate_generation
    from app.services.iot_service import iot_manager

    with _lock:
        if _state == "MANUAL_LATCHED_OPEN":
            _last_decision = decision
            _last_direction = direction
            _last_attempt_id = attempt_id
            logger.info(
                "gate Automated decision=%s recorded while manual-open latch is active; actuator unchanged",
                decision,
            )
            return _state

        _cancel_timer()

        _last_decision = decision
        _last_direction = direction
        _last_attempt_id = attempt_id
        _last_transition_at = datetime.now(timezone.utc)
        _gate_generation += 1

        if decision == "ALLOW":
            _state = "OPEN"
            # Schedule auto-close in simulated memory
            t = threading.Timer(
                open_duration_seconds,
                _auto_close_callback,
                args=(_gate_generation,),
            )
            t.daemon = True
            t.start()
            _auto_close_timer = t
            logger.info(
                "gate OPENED for attempt=%s direction=%s (auto-close in %.1fs)",
                attempt_id, direction, open_duration_seconds,
            )
            # Dispatch physical open command to ESP32
            if dispatch_hardware:
                iot_manager.dispatch_open_command(
                    attempt_id=attempt_id,
                    duration_ms=int(open_duration_seconds * 1000),
                    message="ACCESS GRANTED",
                )
        elif decision == "MANUAL_REVIEW":
            _state = "MANUAL_REVIEW"
            logger.info("gate MANUAL_REVIEW state for attempt=%s", attempt_id)
            # Notify LCD of manual review
            if dispatch_hardware:
                iot_manager.dispatch_display_status("MANUAL REVIEW", "WAIT FOR GUARD")
        else:  # DENY or any unknown decision
            _state = "CLOSED"
            logger.info("gate CLOSED (DENY) for attempt=%s", attempt_id)
            # Notify LCD of access denial
            if dispatch_hardware:
                iot_manager.dispatch_display_status("ACCESS DENIED", "GATE LOCKED")

        return _state


def latch_manual_open(initiated_by: str | None = None) -> GateState:
    """Latch the simulated gate open after the controller acknowledges manual OPEN."""
    global _state, _last_decision, _last_direction, _last_attempt_id
    global _last_transition_at, _gate_generation, _manual_latched_at

    with _lock:
        _cancel_timer()
        _gate_generation += 1
        _state = "MANUAL_LATCHED_OPEN"
        _last_decision = "MANUAL"
        _last_direction = None
        _last_attempt_id = initiated_by
        _last_transition_at = datetime.now(timezone.utc)
        _manual_latched_at = _last_transition_at
        logger.info("gate Manual-open latch enabled by=%s", initiated_by)
        return _state


def sync_controller_status(controller_status: dict) -> None:
    """Clear a stale backend latch after a newer ESP32 startup reports CLOSED."""
    global _state, _last_transition_at, _gate_generation, _manual_latched_at

    if (
        controller_status.get("reported_gate_mode") != "AUTOMATED"
        or controller_status.get("reported_gate_state") != "CLOSED"
        or not controller_status.get("last_heartbeat_at")
    ):
        return

    try:
        reported_at = datetime.fromisoformat(controller_status["last_heartbeat_at"])
    except (TypeError, ValueError):
        logger.warning("gate Ignoring malformed controller heartbeat timestamp")
        return
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)

    with _lock:
        if (
            _state == "MANUAL_LATCHED_OPEN"
            and _manual_latched_at is not None
            and reported_at >= _manual_latched_at
        ):
            _cancel_timer()
            _gate_generation += 1
            _state = "CLOSED"
            _last_transition_at = reported_at
            _manual_latched_at = None
            logger.info("gate Manual-open backend latch cleared by newer controller CLOSED heartbeat")


def force_close(initiated_by: str | None = None, dispatch_hardware: bool = True) -> dict:
    """
    Force the gate to CLOSED state.
    Only authorized security officers or administrators should call this.
    """
    global _state, _last_transition_at, _gate_generation, _manual_latched_at
    from app.services.iot_service import iot_manager

    with _lock:
        _cancel_timer()
        _gate_generation += 1
        _state = "CLOSED"
        _last_transition_at = datetime.now(timezone.utc)
        _manual_latched_at = None
        logger.info("gate Force-closed by=%s", initiated_by)
        # Inform physical display
        if dispatch_hardware:
            iot_manager.dispatch_display_status("GATE CLOSED", "SYSTEM READY")

    return get_status()
