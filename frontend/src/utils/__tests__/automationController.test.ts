/**
 * SmartGuard AI — Automation State Machine Unit Tests
 * Tests the pure state machine in automationController.ts for pause/resume behavior.
 *
 * Run: npx vitest run src/utils/__tests__/automationController.test.ts
 */
import { describe, it, expect } from 'vitest';
import {
  createInitialWorkflowContext,
  startAutomation,
  pauseAutomation,
  resumeAutomation,
  stopAutomation,
  onFaceVerified,
  onPlateVerified,
  onAccessDecision,
  onCameraDisconnect,
  isAutomationRunning,
  isAutomationActive,
  type WorkflowContext,
} from '../automationController';

// ─── Helpers ──────────────────────────────────────────────────────────────────
const WF_ID = 'wf_test_001';
const OTHER_WF = 'wf_other_999';

function buildRunningCtx(state: WorkflowContext['state'] = 'FACE_VERIFICATION'): WorkflowContext {
  const ctx = createInitialWorkflowContext();
  const started = startAutomation(ctx, WF_ID);
  return { ...started, state };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('isAutomationRunning', () => {
  it('returns true for active stages', () => {
    const activeStates: WorkflowContext['state'][] = [
      'INITIALIZING_CAMERA',
      'FACE_VERIFICATION',
      'FACE_VERIFIED',
      'PLATE_VERIFICATION',
      'PLATE_VERIFIED',
      'EVALUATING_ACCESS',
    ];
    for (const s of activeStates) {
      expect(isAutomationRunning(s)).toBe(true);
    }
  });

  it('returns false for PAUSED', () => {
    expect(isAutomationRunning('PAUSED')).toBe(false);
  });

  it('returns false for terminal states', () => {
    const terminals: WorkflowContext['state'][] = [
      'IDLE', 'ACCESS_ALLOWED', 'ACCESS_DENIED', 'MANUAL_REVIEW_REQUIRED', 'ERROR', 'CANCELLED',
    ];
    for (const s of terminals) {
      expect(isAutomationRunning(s)).toBe(false);
    }
  });
});

describe('isAutomationActive', () => {
  it('returns true for PAUSED', () => {
    expect(isAutomationActive('PAUSED')).toBe(true);
  });

  it('returns true for all running stages', () => {
    expect(isAutomationActive('FACE_VERIFICATION')).toBe(true);
  });

  it('returns false for IDLE and terminal states', () => {
    expect(isAutomationActive('IDLE')).toBe(false);
    expect(isAutomationActive('ACCESS_ALLOWED')).toBe(false);
    expect(isAutomationActive('CANCELLED')).toBe(false);
  });
});

describe('startAutomation', () => {
  it('transitions to FACE_VERIFICATION and resets counts', () => {
    const ctx = createInitialWorkflowContext();
    const next = startAutomation(ctx, WF_ID);
    expect(next.state).toBe('FACE_VERIFICATION');
    expect(next.workflowId).toBe(WF_ID);
    expect(next.resumeCheckpoint).toBeNull();
    expect(next.hasEvaluated).toBe(false);
    expect(next.failedFaceAttempts).toBe(0);
    expect(next.verifiedFace).toBeNull();
    expect(next.verifiedPlate).toBeNull();
    expect(next.lastDecision).toBeNull();
  });
});

describe('pauseAutomation', () => {
  it('sets state to PAUSED and saves FACE_VERIFICATION checkpoint', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const paused = pauseAutomation(ctx);
    expect(paused.state).toBe('PAUSED');
    expect(paused.resumeCheckpoint).toBe('FACE_VERIFICATION');
  });

  it('saves FACE_VERIFIED checkpoint when paused during FACE_VERIFIED', () => {
    const ctx = buildRunningCtx('FACE_VERIFIED');
    const paused = pauseAutomation(ctx);
    expect(paused.resumeCheckpoint).toBe('FACE_VERIFIED');
  });

  it('saves PLATE_VERIFICATION checkpoint', () => {
    const ctx = buildRunningCtx('PLATE_VERIFICATION');
    const paused = pauseAutomation(ctx);
    expect(paused.resumeCheckpoint).toBe('PLATE_VERIFICATION');
  });

  it('saves PLATE_VERIFIED checkpoint', () => {
    const ctx = buildRunningCtx('PLATE_VERIFIED');
    const paused = pauseAutomation(ctx);
    expect(paused.resumeCheckpoint).toBe('PLATE_VERIFIED');
  });

  it('saves EVALUATING_ACCESS checkpoint', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const paused = pauseAutomation(ctx);
    expect(paused.resumeCheckpoint).toBe('EVALUATING_ACCESS');
  });

  it('is idempotent — no-op if already paused', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const paused = pauseAutomation(ctx);
    const paused2 = pauseAutomation(paused);
    expect(paused2.state).toBe('PAUSED');
    expect(paused2.resumeCheckpoint).toBe(paused.resumeCheckpoint);
  });

  it('preserves verifiedFace and verifiedPlate when pausing', () => {
    const face = { id: 'person-1', name: 'Alice' };
    const ctx = { ...buildRunningCtx('PLATE_VERIFICATION'), verifiedFace: face };
    const paused = pauseAutomation(ctx);
    expect(paused.verifiedFace).toEqual(face);
  });

  it('preserves failedFaceAttempts when pausing', () => {
    const ctx = { ...buildRunningCtx('FACE_VERIFICATION'), failedFaceAttempts: 2 };
    const paused = pauseAutomation(ctx);
    expect(paused.failedFaceAttempts).toBe(2);
  });

  it('does not pause ACCESS_ALLOWED (terminal)', () => {
    const ctx = buildRunningCtx('ACCESS_ALLOWED');
    const result = pauseAutomation(ctx);
    expect(result.state).toBe('ACCESS_ALLOWED');
  });

  it('does not pause ACCESS_DENIED (terminal)', () => {
    const ctx = buildRunningCtx('ACCESS_DENIED');
    const result = pauseAutomation(ctx);
    expect(result.state).toBe('ACCESS_DENIED');
  });

  it('does not pause MANUAL_REVIEW_REQUIRED (terminal)', () => {
    const ctx = buildRunningCtx('MANUAL_REVIEW_REQUIRED');
    const result = pauseAutomation(ctx);
    expect(result.state).toBe('MANUAL_REVIEW_REQUIRED');
  });

  it('uses custom message when provided', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const paused = pauseAutomation(ctx, 'Camera loss.');
    expect(paused.message).toBe('Camera loss.');
  });
});

describe('resumeAutomation', () => {
  it('is a no-op when not in PAUSED state', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const result = resumeAutomation(ctx);
    expect(result.state).toBe('FACE_VERIFICATION');
  });

  it('is a no-op when workflowId is null', () => {
    const ctx = { ...buildRunningCtx('PAUSED'), workflowId: null, state: 'PAUSED' as const };
    const result = resumeAutomation(ctx);
    expect(result.state).toBe('PAUSED');
  });

  it('errors when userAuthorized is false', () => {
    const ctx = pauseAutomation(buildRunningCtx('FACE_VERIFICATION'));
    const result = resumeAutomation({ ...ctx, userAuthorized: false });
    expect(result.state).toBe('ERROR');
  });

  it('errors when camera is not live', () => {
    const ctx = pauseAutomation(buildRunningCtx('FACE_VERIFICATION'));
    const result = resumeAutomation({ ...ctx, cameraLive: false });
    expect(result.state).toBe('ERROR');
  });

  it('resumes from FACE_VERIFICATION checkpoint to FACE_VERIFICATION', () => {
    const ctx = pauseAutomation(buildRunningCtx('FACE_VERIFICATION'));
    const resumed = resumeAutomation(ctx);
    expect(resumed.state).toBe('FACE_VERIFICATION');
    expect(resumed.resumeCheckpoint).toBeNull();
  });

  it('resumes from FACE_VERIFIED checkpoint to PLATE_VERIFICATION when face data exists', () => {
    const base = { ...buildRunningCtx('FACE_VERIFIED'), verifiedFace: { id: 'person-1', name: 'Alice' } };
    const paused = pauseAutomation(base);
    expect(paused.resumeCheckpoint).toBe('FACE_VERIFIED');
    const resumed = resumeAutomation(paused);
    expect(resumed.state).toBe('PLATE_VERIFICATION');
  });

  it('restarts face stage from FACE_VERIFIED when verifiedFace is null', () => {
    const base = buildRunningCtx('FACE_VERIFIED'); // verifiedFace is null
    const paused = pauseAutomation(base);
    const resumed = resumeAutomation(paused);
    expect(resumed.state).toBe('FACE_VERIFICATION');
  });

  it('resumes from PLATE_VERIFICATION checkpoint to PLATE_VERIFICATION', () => {
    const ctx = pauseAutomation(buildRunningCtx('PLATE_VERIFICATION'));
    const resumed = resumeAutomation(ctx);
    expect(resumed.state).toBe('PLATE_VERIFICATION');
    expect(resumed.resumeCheckpoint).toBeNull();
  });

  it('resumes from PLATE_VERIFIED/EVALUATING_ACCESS to EVALUATING_ACCESS when both verified', () => {
    const base = {
      ...buildRunningCtx('PLATE_VERIFIED'),
      verifiedFace: { id: 'p1', name: 'Bob' },
      verifiedPlate: { plate: 'TN01AB1234' },
    };
    const paused = pauseAutomation(base);
    const resumed = resumeAutomation(paused);
    expect(resumed.state).toBe('EVALUATING_ACCESS');
    expect(resumed.hasEvaluated).toBe(true);
  });

  it('restarts face from EVALUATING_ACCESS when face data missing', () => {
    const base = {
      ...buildRunningCtx('EVALUATING_ACCESS'),
      verifiedFace: null,
      verifiedPlate: { plate: 'TN01AB1234' },
    };
    const paused = pauseAutomation(base);
    const resumed = resumeAutomation(paused);
    expect(resumed.state).toBe('FACE_VERIFICATION');
  });

  it('clears resumeCheckpoint after resume', () => {
    const ctx = pauseAutomation(buildRunningCtx('PLATE_VERIFICATION'));
    const resumed = resumeAutomation(ctx);
    expect(resumed.resumeCheckpoint).toBeNull();
  });

  it('Stop overrides Resume — cancelled workflow cannot be resumed', () => {
    const paused = pauseAutomation(buildRunningCtx('FACE_VERIFICATION'));
    const stopped = stopAutomation(paused);
    expect(stopped.state).toBe('CANCELLED');
    expect(stopped.workflowId).toBeNull();
    const resumed = resumeAutomation(stopped);
    // workflowId is null so it is a no-op
    expect(resumed.state).toBe('CANCELLED');
  });
});

describe('stopAutomation', () => {
  it('sets state to CANCELLED and clears workflowId', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const stopped = stopAutomation(ctx);
    expect(stopped.state).toBe('CANCELLED');
    expect(stopped.workflowId).toBeNull();
    expect(stopped.resumeCheckpoint).toBeNull();
  });

  it('stops even when paused', () => {
    const paused = pauseAutomation(buildRunningCtx('PLATE_VERIFICATION'));
    const stopped = stopAutomation(paused);
    expect(stopped.state).toBe('CANCELLED');
  });
});

describe('onFaceVerified', () => {
  it('transitions to FACE_VERIFIED when in FACE_VERIFICATION with matching workflowId', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const result = onFaceVerified(ctx, WF_ID, { id: 'p1', name: 'Alice' });
    expect(result.state).toBe('FACE_VERIFIED');
    expect(result.verifiedFace?.name).toBe('Alice');
  });

  it('is a no-op for wrong workflowId', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const result = onFaceVerified(ctx, OTHER_WF, { id: 'p1' });
    expect(result.state).toBe('FACE_VERIFICATION');
    expect(result.verifiedFace).toBeNull();
  });

  it('is a no-op when PAUSED', () => {
    const paused = pauseAutomation(buildRunningCtx('FACE_VERIFICATION'));
    const result = onFaceVerified(paused, WF_ID, { id: 'p1' });
    // PAUSED !== FACE_VERIFICATION so no state transition
    expect(result.state).toBe('PAUSED');
  });
});

describe('onPlateVerified', () => {
  it('transitions to PLATE_VERIFIED with matching workflowId', () => {
    const ctx = buildRunningCtx('PLATE_VERIFICATION');
    const result = onPlateVerified(ctx, WF_ID, { plate: 'TN01AB1234', status: 'registered' });
    expect(result.state).toBe('PLATE_VERIFIED');
    expect(result.verifiedPlate?.plate).toBe('TN01AB1234');
  });

  it('is a no-op for wrong workflowId', () => {
    const ctx = buildRunningCtx('PLATE_VERIFICATION');
    const result = onPlateVerified(ctx, OTHER_WF, { plate: 'TN01AB9999' });
    expect(result.state).toBe('PLATE_VERIFICATION');
  });
});

describe('onAccessDecision', () => {
  it('ALLOW: transitions to ACCESS_ALLOWED with gate OPEN', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const result = onAccessDecision(ctx, WF_ID, 'ALLOW');
    expect(result.state).toBe('ACCESS_ALLOWED');
    expect(result.gateStatus).toBe('OPEN');
    expect(result.lastDecision).toBe('ALLOW');
    expect(result.resumeCheckpoint).toBeNull();
  });

  it('DENY: transitions to ACCESS_DENIED with gate CLOSED', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const result = onAccessDecision(ctx, WF_ID, 'DENY', 'Watchlist match');
    expect(result.state).toBe('ACCESS_DENIED');
    expect(result.gateStatus).toBe('CLOSED');
    expect(result.lastDecision).toBe('DENY');
  });

  it('MANUAL_REVIEW: transitions to MANUAL_REVIEW_REQUIRED', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const result = onAccessDecision(ctx, WF_ID, 'MANUAL_REVIEW', 'Unregistered vehicle');
    expect(result.state).toBe('MANUAL_REVIEW_REQUIRED');
    expect(result.gateStatus).toBe('MANUAL_REVIEW');
  });

  it('is a no-op for wrong workflowId', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const result = onAccessDecision(ctx, OTHER_WF, 'ALLOW');
    expect(result.state).toBe('EVALUATING_ACCESS');
  });

  it('DENY cannot be paused or resumed — gate security policy', () => {
    const ctx = buildRunningCtx('EVALUATING_ACCESS');
    const denied = onAccessDecision(ctx, WF_ID, 'DENY');
    // Cannot pause a DENY result
    const paused = pauseAutomation(denied);
    expect(paused.state).toBe('ACCESS_DENIED');
    // Cannot resume
    const resumed = resumeAutomation(paused);
    expect(resumed.state).toBe('ACCESS_DENIED');
  });
});

describe('onCameraDisconnect', () => {
  it('auto-pauses when automation is running', () => {
    const ctx = buildRunningCtx('PLATE_VERIFICATION');
    const result = onCameraDisconnect(ctx);
    expect(result.state).toBe('PAUSED');
    expect(result.cameraLive).toBe(false);
    expect(result.resumeCheckpoint).toBe('PLATE_VERIFICATION');
  });

  it('does not change state when automation is idle', () => {
    const ctx = createInitialWorkflowContext();
    const result = onCameraDisconnect(ctx);
    expect(result.state).toBe('IDLE');
    expect(result.cameraLive).toBe(false);
  });

  it('cannot resume after disconnect without camera being restored', () => {
    const ctx = buildRunningCtx('FACE_VERIFICATION');
    const disconnected = onCameraDisconnect(ctx);
    expect(disconnected.state).toBe('PAUSED');
    // Camera is not live, resume should error
    const resumeAttempt = resumeAutomation(disconnected);
    expect(resumeAttempt.state).toBe('ERROR');
  });
});

describe('complete happy-path workflow', () => {
  it('runs IDLE → FACE_VERIFICATION → FACE_VERIFIED → PLATE_VERIFICATION → PLATE_VERIFIED → EVALUATING_ACCESS → ACCESS_ALLOWED', () => {
    let ctx = createInitialWorkflowContext();

    ctx = startAutomation(ctx, WF_ID);
    expect(ctx.state).toBe('FACE_VERIFICATION');

    ctx = onFaceVerified(ctx, WF_ID, { id: 'p1', name: 'Alice' });
    expect(ctx.state).toBe('FACE_VERIFIED');

    // Simulate transition to PLATE_VERIFICATION
    ctx = { ...ctx, state: 'PLATE_VERIFICATION' };

    ctx = onPlateVerified(ctx, WF_ID, { plate: 'TN01AB1234' });
    expect(ctx.state).toBe('PLATE_VERIFIED');

    ctx = { ...ctx, state: 'EVALUATING_ACCESS' };

    ctx = onAccessDecision(ctx, WF_ID, 'ALLOW');
    expect(ctx.state).toBe('ACCESS_ALLOWED');
    expect(ctx.gateStatus).toBe('OPEN');
  });
});

describe('pause-mid-workflow then resume happy-path', () => {
  it('pauses at PLATE_VERIFICATION, resumes, and eventually completes', () => {
    let ctx = createInitialWorkflowContext();

    ctx = startAutomation(ctx, WF_ID);
    ctx = onFaceVerified(ctx, WF_ID, { id: 'p1', name: 'Alice' });
    ctx = { ...ctx, state: 'PLATE_VERIFICATION' };

    // Officer pauses
    ctx = pauseAutomation(ctx);
    expect(ctx.state).toBe('PAUSED');
    expect(ctx.resumeCheckpoint).toBe('PLATE_VERIFICATION');
    expect(ctx.verifiedFace).not.toBeNull();

    // Officer resumes
    ctx = resumeAutomation(ctx);
    expect(ctx.state).toBe('PLATE_VERIFICATION');

    // Plate is now verified
    ctx = onPlateVerified(ctx, WF_ID, { plate: 'TN01AB5678' });
    expect(ctx.state).toBe('PLATE_VERIFIED');

    ctx = { ...ctx, state: 'EVALUATING_ACCESS' };
    ctx = onAccessDecision(ctx, WF_ID, 'ALLOW');
    expect(ctx.state).toBe('ACCESS_ALLOWED');
  });
});
