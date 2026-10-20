// SmartGuard AI — Automated Verification Workflow & Pause/Resume State Machine Controller

export type AutomationState =
  | 'IDLE'
  | 'INITIALIZING_CAMERA'
  | 'FACE_VERIFICATION'
  | 'FACE_VERIFIED'
  | 'PLATE_VERIFICATION'
  | 'PLATE_VERIFIED'
  | 'EVALUATING_ACCESS'
  | 'PAUSED'
  | 'ACCESS_ALLOWED'
  | 'ACCESS_DENIED'
  | 'MANUAL_REVIEW_REQUIRED'
  | 'ERROR'
  | 'CANCELLED';

export type ResumeCheckpoint =
  | 'FACE_VERIFICATION'
  | 'FACE_VERIFIED'
  | 'PLATE_VERIFICATION'
  | 'PLATE_VERIFIED'
  | 'EVALUATING_ACCESS'
  | null;

export interface WorkflowContext {
  workflowId: string | null;
  state: AutomationState;
  resumeCheckpoint: ResumeCheckpoint;
  message: string;
  hasEvaluated: boolean;
  failedFaceAttempts: number;
  cameraLive: boolean;
  userAuthorized: boolean;
  verifiedFace: { id: string; name?: string } | null;
  verifiedPlate: { plate: string; status?: string } | null;
  gateStatus: 'CLOSED' | 'OPEN' | 'MANUAL_REVIEW';
  lastDecision: 'ALLOW' | 'DENY' | 'MANUAL_REVIEW' | null;
}

export function createInitialWorkflowContext(): WorkflowContext {
  return {
    workflowId: null,
    state: 'IDLE',
    resumeCheckpoint: null,
    message: 'Ready to start automation.',
    hasEvaluated: false,
    failedFaceAttempts: 0,
    cameraLive: true,
    userAuthorized: true,
    verifiedFace: null,
    verifiedPlate: null,
    gateStatus: 'CLOSED',
    lastDecision: null,
  };
}

export function isAutomationRunning(state: AutomationState): boolean {
  return (
    state !== 'IDLE' &&
    state !== 'PAUSED' &&
    state !== 'ACCESS_ALLOWED' &&
    state !== 'ACCESS_DENIED' &&
    state !== 'MANUAL_REVIEW_REQUIRED' &&
    state !== 'ERROR' &&
    state !== 'CANCELLED'
  );
}

export function isAutomationActive(state: AutomationState): boolean {
  return isAutomationRunning(state) || state === 'PAUSED';
}

/**
 * 1. Start Automation
 */
export function startAutomation(ctx: WorkflowContext, workflowId: string): WorkflowContext {
  return {
    ...ctx,
    workflowId,
    state: 'FACE_VERIFICATION',
    resumeCheckpoint: null,
    message: 'Stage 1 active: Hold still while identity is verified...',
    hasEvaluated: false,
    failedFaceAttempts: 0,
    verifiedFace: null,
    verifiedPlate: null,
    lastDecision: null,
  };
}

/**
 * 2. Pause Automation
 * Idempotent, preserves attempt counters and completed verification results.
 */
export function pauseAutomation(ctx: WorkflowContext, reasonMsg?: string): WorkflowContext {
  // If not running or already paused, idempotent no-op
  if (!isAutomationRunning(ctx.state) || ctx.state === 'PAUSED') {
    return ctx;
  }

  // Terminal states cannot be paused
  if (
    ctx.state === 'ACCESS_ALLOWED' ||
    ctx.state === 'ACCESS_DENIED' ||
    ctx.state === 'MANUAL_REVIEW_REQUIRED' ||
    ctx.state === 'CANCELLED'
  ) {
    return ctx;
  }

  // Determine safe checkpoint
  let cp: ResumeCheckpoint = 'FACE_VERIFICATION';
  if (ctx.state === 'FACE_VERIFICATION' || ctx.state === 'INITIALIZING_CAMERA') {
    cp = 'FACE_VERIFICATION';
  } else if (ctx.state === 'FACE_VERIFIED') {
    cp = 'FACE_VERIFIED';
  } else if (ctx.state === 'PLATE_VERIFICATION') {
    cp = 'PLATE_VERIFICATION';
  } else if (ctx.state === 'PLATE_VERIFIED') {
    cp = 'PLATE_VERIFIED';
  } else if (ctx.state === 'EVALUATING_ACCESS') {
    cp = 'EVALUATING_ACCESS';
  }

  return {
    ...ctx,
    state: 'PAUSED',
    resumeCheckpoint: cp,
    message: reasonMsg || 'Automation is paused. Verification will not proceed until you resume.',
  };
}

/**
 * 3. Resume Automation
 * Validates session, camera, and verification validity. Resumes from safe checkpoint.
 */
export function resumeAutomation(ctx: WorkflowContext): WorkflowContext {
  // Can only resume from PAUSED state with active workflow
  if (!ctx.workflowId || ctx.state !== 'PAUSED') {
    return ctx;
  }

  // Session check
  if (!ctx.userAuthorized) {
    return {
      ...ctx,
      state: 'ERROR',
      message: 'Unauthorized session. Please log in again to resume automation.',
      resumeCheckpoint: null,
    };
  }

  // Camera check
  if (!ctx.cameraLive) {
    return {
      ...ctx,
      state: 'ERROR',
      message: 'Camera unavailable. Restore camera to resume automation.',
      resumeCheckpoint: null,
    };
  }

  const cp = ctx.resumeCheckpoint || 'FACE_VERIFICATION';

  switch (cp) {
    case 'FACE_VERIFICATION':
      return {
        ...ctx,
        state: 'FACE_VERIFICATION',
        resumeCheckpoint: null,
        message: 'Stage 1 active (resumed): Hold still while identity is verified...',
      };

    case 'FACE_VERIFIED':
      if (ctx.verifiedFace) {
        return {
          ...ctx,
          state: 'PLATE_VERIFICATION',
          resumeCheckpoint: null,
          message: 'Stage 2 active (resumed): Move vehicle into camera view...',
        };
      } else {
        return {
          ...ctx,
          state: 'FACE_VERIFICATION',
          resumeCheckpoint: null,
          message: 'Face verification expired. Re-scanning identity...',
        };
      }

    case 'PLATE_VERIFICATION':
      return {
        ...ctx,
        state: 'PLATE_VERIFICATION',
        resumeCheckpoint: null,
        message: 'Stage 2 active (resumed): Move vehicle into camera view...',
      };

    case 'PLATE_VERIFIED':
    case 'EVALUATING_ACCESS':
      if (ctx.verifiedPlate && ctx.verifiedFace) {
        return {
          ...ctx,
          state: 'EVALUATING_ACCESS',
          resumeCheckpoint: null,
          hasEvaluated: true,
          message: 'Evaluating access decision with campus security engine...',
        };
      } else if (!ctx.verifiedFace) {
        return {
          ...ctx,
          state: 'FACE_VERIFICATION',
          resumeCheckpoint: null,
          message: 'Face evidence expired. Restarting face stage...',
        };
      } else {
        return {
          ...ctx,
          state: 'PLATE_VERIFICATION',
          resumeCheckpoint: null,
          message: 'Plate evidence missing. Re-scanning vehicle...',
        };
      }

    default:
      return {
        ...ctx,
        state: 'FACE_VERIFICATION',
        resumeCheckpoint: null,
        message: 'Resuming verification workflow...',
      };
  }
}

/**
 * 4. Stop Automation
 * Permanently cancels automatic progression.
 */
export function stopAutomation(ctx: WorkflowContext): WorkflowContext {
  return {
    ...ctx,
    workflowId: null,
    resumeCheckpoint: null,
    state: 'CANCELLED',
    message: 'Automation cancelled by security officer.',
  };
}

/**
 * 5. Handle Face Match Event
 * Advances state only if currently in FACE_VERIFICATION. Ignored if PAUSED, CANCELLED, or wrong workflow.
 */
export function onFaceVerified(
  ctx: WorkflowContext,
  workflowId: string,
  person: { id: string; name?: string }
): WorkflowContext {
  if (ctx.workflowId !== workflowId || ctx.state !== 'FACE_VERIFICATION') {
    return ctx;
  }
  return {
    ...ctx,
    state: 'FACE_VERIFIED',
    verifiedFace: person,
    message: `Identity verified (${person.name || 'Matched'}). Automatically advancing to plate recognition...`,
  };
}

/**
 * 6. Handle Plate Match Event
 * Advances state only if currently in PLATE_VERIFICATION. Ignored if PAUSED, CANCELLED, or wrong workflow.
 */
export function onPlateVerified(
  ctx: WorkflowContext,
  workflowId: string,
  plate: { plate: string; status?: string }
): WorkflowContext {
  if (ctx.workflowId !== workflowId || ctx.state !== 'PLATE_VERIFICATION') {
    return ctx;
  }
  return {
    ...ctx,
    state: 'PLATE_VERIFIED',
    verifiedPlate: plate,
    message: `Number plate detected (${plate.plate}). Evaluating gate access...`,
  };
}

/**
 * 7. Handle Access Decision Event
 * Reconciles authoritative backend decision (ALLOW / DENY / MANUAL_REVIEW).
 * Even if paused while in flight, backend decision is committed and gate state reflects reality.
 */
export function onAccessDecision(
  ctx: WorkflowContext,
  workflowId: string,
  decision: 'ALLOW' | 'DENY' | 'MANUAL_REVIEW',
  reason?: string
): WorkflowContext {
  if (ctx.workflowId !== workflowId) {
    return ctx;
  }

  if (decision === 'ALLOW') {
    return {
      ...ctx,
      state: 'ACCESS_ALLOWED',
      resumeCheckpoint: null,
      lastDecision: 'ALLOW',
      gateStatus: 'OPEN',
      message: 'Access Permitted: Gate barrier opening. Auto-close in 15s.',
    };
  } else if (decision === 'DENY') {
    return {
      ...ctx,
      state: 'ACCESS_DENIED',
      resumeCheckpoint: null,
      lastDecision: 'DENY',
      gateStatus: 'CLOSED',
      message: `Automation stopped — access denied (${reason || 'Policy denial'}). Security officer action required.`,
    };
  } else {
    return {
      ...ctx,
      state: 'MANUAL_REVIEW_REQUIRED',
      resumeCheckpoint: null,
      lastDecision: 'MANUAL_REVIEW',
      gateStatus: 'MANUAL_REVIEW',
      message: `Automation stopped — security approval required (${reason || 'Manual review queued'}).`,
    };
  }
}

/**
 * 8. Automatic Pause on Camera Loss
 */
export function onCameraDisconnect(ctx: WorkflowContext): WorkflowContext {
  const updated = { ...ctx, cameraLive: false };
  if (isAutomationRunning(ctx.state)) {
    return pauseAutomation(updated, 'Camera stream disconnected. Automation paused for safety.');
  }
  return updated;
}
