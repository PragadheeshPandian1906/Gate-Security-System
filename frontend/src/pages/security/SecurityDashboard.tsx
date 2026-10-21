// SmartGuard AI — User Entry Management & Security Operations Center Terminal
// Integrated Face Verification (InsightFace), Number Plate Recognition (FastALPR),
// Phase 3 Access Decision Engine, Simulated Gate Control, and Automated Verification Workflow.
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Camera,
  Car,
  ScanFace,
  Activity,
  Play,
  Pause,
  Square,
  RefreshCw,
  Clock,
  Cpu,
  Sliders,
  ChevronDown,
  Cloud,
  CheckCircle2,
  HardDrive,
  ArrowDownCircle,
  ArrowUpCircle,
  AlertTriangle,
  Shield,
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  ClipboardList,
  ListFilter,
  Lock,
  Unlock,
  Eye,
  X,
  List,
  RotateCcw,
  UserCheck,
  UserPlus,
  Calendar,
  CheckCircle,
  HelpCircle,
  Workflow,
  QrCode,
} from 'lucide-react';
import { visitorsApi } from '../../api/visitors';
import { useAuth } from '../../context/AuthContext';
import { aiApi, type LiveFaceDetection, type LivePlateDetection, type AiDiagnostics } from '../../api/phase2';
import {
  accessApi,
  gateApi,
  watchlistApi,
  scheduleApi,
  type AccessAttemptSummary,
  type GateStatus,
  type WatchlistEntry,
  type ScheduleResponse,
  type Direction,
} from '../../api/phase3';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { CampusEntryOverview } from '../../components/security/CampusEntryOverview';

// ── State Types ───────────────────────────────────────────────────────────────

type CameraStatus = 'idle' | 'starting' | 'live' | 'permission_denied' | 'unavailable';

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

export type FaceStageState =
  | 'NOT_STARTED'
  | 'CAMERA_STARTING'
  | 'SCANNING'
  | 'FACE_DETECTED'
  | 'VERIFYING'
  | 'VERIFIED'
  | 'FAILED'
  | 'MAX_ATTEMPTS_REACHED'
  | 'ERROR'
  | 'CANCELLED';

export type PlateStageState =
  | 'NOT_STARTED'
  | 'SCANNING'
  | 'PLATE_DETECTED'
  | 'REGISTERED'
  | 'UNREGISTERED'
  | 'FLAGGED'
  | 'ERROR'
  | 'CANCELLED';

interface DetectionHistoryItem {
  id: string;
  type: 'face' | 'plate';
  label: string;
  subLabel?: string;
  timestamp: Date;
  status: string;
  score?: number | null;
}

export function SecurityDashboard() {
  const { user, token } = useAuth();
  const navigate = useNavigate();

  // ── Tab Navigation ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'terminal' | 'audit' | 'watchlist' | 'schedule' | 'diagnostics'>('terminal');

  // ── Camera and Streaming States ─────────────────────────────────────────────
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>('idle');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [captureIntervalMs, setCaptureIntervalMs] = useState<number>(2000);

  // ── Workflow Direction & Confirmation ───────────────────────────────────────
  const [direction, setDirection] = useState<Direction>('ENTRY');
  const [pendingDirectionChange, setPendingDirectionChange] = useState<Direction | null>(null);

  // ── Automated Verification Workflow State Machine ───────────────────────────
  const [automationState, setAutomationState] = useState<AutomationState>('IDLE');
  const [automationMsg, setAutomationMsg] = useState<string>('Ready: Click "Start Automation" to automatically verify face, recognize vehicle, and evaluate gate access.');
  const [resumeCheckpoint, setResumeCheckpoint] = useState<ResumeCheckpoint>(null);
  const automationStateRef = useRef<AutomationState>('IDLE');
  const resumeCheckpointRef = useRef<ResumeCheckpoint>(null);
  const isEvaluatingInFlightRef = useRef<boolean>(false);
  useEffect(() => {
    automationStateRef.current = automationState;
  }, [automationState]);
  useEffect(() => {
    resumeCheckpointRef.current = resumeCheckpoint;
  }, [resumeCheckpoint]);
  const workflowIdRef = useRef<string | null>(null);
  const hasEvaluatedRef = useRef<boolean>(false);

  // ── Guided Stage States ─────────────────────────────────────────────────────
  const [faceStageState, setFaceStageState] = useState<FaceStageState>('NOT_STARTED');
  const [failedFaceAttempts, setFailedFaceAttempts] = useState<number>(0);
  const [faceGuidance, setFaceGuidance] = useState<string>('Click "Start Face Verification" or "Start Automation" to begin scanning.');
  const [verifiedFace, setVerifiedFace] = useState<LiveFaceDetection | null>(null);

  const [plateStageState, setPlateStageState] = useState<PlateStageState>('NOT_STARTED');
  const [plateGuidance, setPlateGuidance] = useState<string>('Click "Start Plate Verification" when vehicle is positioned.');
  const [verifiedPlate, setVerifiedPlate] = useState<LivePlateDetection | null>(null);

  // ── Telemetry & Metrics ─────────────────────────────────────────────────────
  const [fps, setFps] = useState<number>(0);
  const [lastTiming, setLastTiming] = useState<{ total: number; face: number; plate: number } | null>(null);
  const [currentFaces, setCurrentFaces] = useState<LiveFaceDetection[]>([]);
  const [currentPlates, setCurrentPlates] = useState<LivePlateDetection[]>([]);
  const [history, setHistory] = useState<DetectionHistoryItem[]>([]);
  const [diagnostics, setDiagnostics] = useState<AiDiagnostics | null>(null);

  // ── Snapshot & Evidence Storage ─────────────────────────────────────────────
  const [isSavingSnapshot, setIsSavingSnapshot] = useState(false);
  const [snapshotMsg, setSnapshotMsg] = useState<string | null>(null);
  const [lastSavedStorage, setLastSavedStorage] = useState<{ local_ok: boolean; remote_ok: boolean; storage_path?: string | null } | null>(null);

  // ── Phase 3 Decision Engine & Gate Control ──────────────────────────────────
  const [gateStatus, setGateStatus] = useState<GateStatus | null>(null);
  const [isGateOperating, setIsGateOperating] = useState<boolean>(false);
  const [gateFeedback, setGateFeedback] = useState<string | null>(null);
  const isGateWsConnectedRef = useRef(false);

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined;
    let fallbackInFlight = false;

    const pollGateStatusWhenDisconnected = async () => {
      if (!active) return;
      if (!isGateWsConnectedRef.current && !fallbackInFlight) {
        fallbackInFlight = true;
        try {
          const response = await gateApi.getStatus();
          if (active) setGateStatus(response.data);
        } catch (error) {
          console.warn('Gate status fallback request failed', error);
        } finally {
          fallbackInFlight = false;
        }
      }
      if (active) {
        fallbackTimer = setTimeout(pollGateStatusWhenDisconnected, 2500);
      }
    };

    const connectMonitor = () => {
      if (!active || !token) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.hostname}:8000/ws/gate/monitor?token=${encodeURIComponent(token)}`;
      try {
        socket = new WebSocket(wsUrl);
        socket.onopen = () => {
          isGateWsConnectedRef.current = true;
        };
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'INIT' && payload.gate_status) {
              setGateStatus(payload.gate_status);
            } else if (payload.type === 'STATUS_UPDATE' && payload.gate_status) {
              setGateStatus(payload.gate_status);
            }
          } catch (error) {
            console.warn('Failed to parse gate monitor update', error);
          }
        };
        socket.onclose = () => {
          isGateWsConnectedRef.current = false;
          if (active) reconnectTimer = setTimeout(connectMonitor, 4000);
        };
        socket.onerror = () => {
          isGateWsConnectedRef.current = false;
        };
      } catch (error) {
        console.warn('Gate monitor WebSocket connection failed', error);
        isGateWsConnectedRef.current = false;
        if (active) reconnectTimer = setTimeout(connectMonitor, 4000);
      }
    };

    connectMonitor();
    fallbackTimer = setTimeout(pollGateStatusWhenDisconnected, 2500);

    return () => {
      active = false;
      isGateWsConnectedRef.current = false;
      if (fallbackTimer) clearTimeout(fallbackTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  const handleManualOpenGate = async () => {
    setIsGateOperating(true);
    setGateFeedback(null);
    try {
      const res = await gateApi.open();
      setGateStatus(res.data.status);
      const hardware = res.data.hardware;
      setGateFeedback(hardware.controller_acknowledged
        ? 'Manual-open latch active; controller reports OPEN. Physical position is not sensor-verified.'
        : hardware.delivered
        ? `Open command delivered; controller acknowledgement unavailable (${hardware.error || hardware.status}).`
        : `Open command was not delivered (${hardware.error || hardware.status}).`);
      setTimeout(() => setGateFeedback(null), 4000);
    } catch (err: any) {
      setGateFeedback('Failed to open gate: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsGateOperating(false);
    }
  };

  const handleManualCloseGate = async () => {
    setIsGateOperating(true);
    setGateFeedback(null);
    try {
      const res = await gateApi.close();
      setGateStatus(res.data.status);
      const hardware = res.data.hardware;
      setGateFeedback(hardware.controller_acknowledged
        ? 'Manual close acknowledged; controller reports CLOSED. Physical position is not sensor-verified.'
        : hardware.delivered
        ? `Close command delivered; controller acknowledgement unavailable (${hardware.error || hardware.status}).`
        : `Close command was not delivered (${hardware.error || hardware.status}).`);
      setTimeout(() => setGateFeedback(null), 4000);
    } catch (err: any) {
      setGateFeedback('Failed to close gate: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsGateOperating(false);
    }
  };
  const [accessHistory, setAccessHistory] = useState<AccessAttemptSummary[]>([]);
  const [pendingReviews, setPendingReviews] = useState<AccessAttemptSummary[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [scheduleData, setScheduleData] = useState<ScheduleResponse | null>(null);
  const [lastDecision, setLastDecision] = useState<AccessAttemptSummary | null>(null);
  const [isSubmittingAttempt, setIsSubmittingAttempt] = useState(false);
  const [accessError, setAccessError] = useState<string | null>(null);
  const isPhase3RefreshInFlightRef = useRef(false);
  const isWatchlistRefreshInFlightRef = useRef(false);

  // ── Manual Review Resolution ────────────────────────────────────────────────
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const [isResolvingReview, setIsResolvingReview] = useState(false);

  // ── Visitor Management Modal ────────────────────────────────────────────────
  const [isVisitorModalOpen, setIsVisitorModalOpen] = useState(false);
  const [visitorName, setVisitorName] = useState('');
  const [visitorPlate, setVisitorPlate] = useState('');
  const [visitorHost, setVisitorHost] = useState('');
  const [visitorPurpose, setVisitorPurpose] = useState('Campus Meeting');
  const [visitorSuccessMsg, setVisitorSuccessMsg] = useState<string | null>(null);

  // ── Refs ────────────────────────────────────────────────────────────────────
  const faceVideoRef = useRef<HTMLVideoElement | null>(null);
  const faceOverlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const faceContainerRef = useRef<HTMLDivElement | null>(null);

  const plateVideoRef = useRef<HTMLVideoElement | null>(null);
  const plateOverlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const plateContainerRef = useRef<HTMLDivElement | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const intervalTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isProcessingRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const frameCountRef = useRef<number>(0);
  const lastFpsCalcTimeRef = useRef<number>(performance.now());
  const cooldownMapRef = useRef<Map<string, number>>(new Map());

  // Attempt debounce timer and attempt tracker
  const lastFailedAttemptTimeRef = useRef<number>(0);
  const failedAttemptsCountRef = useRef<number>(0);

  // Verification IDs stored for backend access evaluation
  const lastFaceVerIdRef = useRef<string | null>(null);
  const lastAlprVerIdRef = useRef<string | null>(null);

  // ── Load Diagnostics & Initial Data ─────────────────────────────────────────
  useEffect(() => {
    aiApi.getDiagnostics()
      .then((res) => setDiagnostics(res.data))
      .catch((err) => console.warn('Could not load AI diagnostics:', err));

    scheduleApi.get()
      .then((res) => setScheduleData(res.data))
      .catch((err) => console.warn('Could not load campus schedule:', err));
  }, []);

  // ── Enumerate Video Input Devices ───────────────────────────────────────────
  const refreshDevices = useCallback(async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === 'videoinput');
      setVideoDevices(videoInputs);
      if (videoInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(videoInputs[0].deviceId);
      }
    } catch (err) {
      console.warn('Failed to enumerate media devices:', err);
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    refreshDevices();
  }, [refreshDevices]);

  // ── Clear Canvas Overlays ───────────────────────────────────────────────────
  const clearOverlays = useCallback(() => {
    const fc = faceOverlayCanvasRef.current;
    if (fc) {
      const ctx = fc.getContext('2d');
      ctx?.clearRect(0, 0, fc.width, fc.height);
    }
    const pc = plateOverlayCanvasRef.current;
    if (pc) {
      const ctx = pc.getContext('2d');
      ctx?.clearRect(0, 0, pc.width, pc.height);
    }
    setCurrentFaces([]);
    setCurrentPlates([]);
  }, []);

  // ── Draw Face Bounding Boxes ────────────────────────────────────────────────
  const drawFaceDetections = useCallback((faces: LiveFaceDetection[], imageW: number, imageH: number) => {
    const canvas = faceOverlayCanvasRef.current;
    const video = faceVideoRef.current;
    const container = faceContainerRef.current;
    if (!canvas || !video || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const videoW = video.videoWidth || imageW || 640;
    const videoH = video.videoHeight || imageH || 480;
    const videoAspect = videoW / videoH;
    const containerAspect = rect.width / rect.height;

    let renderW = rect.width;
    let renderH = rect.height;
    let offsetX = 0;
    let offsetY = 0;

    if (containerAspect > videoAspect) {
      renderH = rect.height;
      renderW = renderH * videoAspect;
      offsetX = (rect.width - renderW) / 2;
    } else {
      renderW = rect.width;
      renderH = renderW / videoAspect;
      offsetY = (rect.height - renderH) / 2;
    }

    const scaleX = renderW / (imageW || videoW);
    const scaleY = renderH / (imageH || videoH);

    faces.forEach((face) => {
      if (!face.box || face.box.length < 4) return;
      const x = offsetX + face.box[0] * scaleX;
      const y = offsetY + face.box[1] * scaleY;
      const w = (face.box[2] - face.box[0]) * scaleX;
      const h = (face.box[3] - face.box[1]) * scaleY;

      let strokeColor = '#06b6d4';
      let bgChipColor = 'rgba(6, 182, 212, 0.25)';
      let textColor = '#22d3ee';

      if (face.status === 'matched') {
        strokeColor = '#10b981';
        bgChipColor = 'rgba(16, 185, 129, 0.25)';
        textColor = '#34d399';
      } else if (face.status === 'low_confidence') {
        strokeColor = '#f59e0b';
        bgChipColor = 'rgba(245, 158, 11, 0.25)';
        textColor = '#fbbf24';
      } else if (face.status === 'unknown') {
        strokeColor = '#f43f5e';
        bgChipColor = 'rgba(244, 63, 94, 0.25)';
        textColor = '#fb7185';
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = strokeColor;
      ctx.shadowBlur = 8;
      ctx.strokeRect(x, y, w, h);

      const bLen = Math.min(16, w * 0.25, h * 0.25);
      ctx.lineWidth = 3.5;
      ctx.beginPath();
      ctx.moveTo(x, y + bLen); ctx.lineTo(x, y); ctx.lineTo(x + bLen, y);
      ctx.moveTo(x + w - bLen, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + bLen);
      ctx.moveTo(x, y + h - bLen); ctx.lineTo(x, y + h); ctx.lineTo(x + bLen, y + h);
      ctx.moveTo(x + w - bLen, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - bLen);
      ctx.stroke();
      ctx.shadowBlur = 0;

      const labelText = face.label || 'Face';
      ctx.font = '600 11px Inter, sans-serif';
      const textMetrics = ctx.measureText(labelText);
      const chipW = textMetrics.width + 12;
      const chipH = 20;
      const chipX = x;
      const chipY = Math.max(offsetY, y - chipH - 4);

      ctx.fillStyle = 'rgba(10, 15, 29, 0.9)';
      ctx.fillRect(chipX, chipY, chipW, chipH);
      ctx.fillStyle = bgChipColor;
      ctx.fillRect(chipX, chipY, chipW, chipH);
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.strokeRect(chipX, chipY, chipW, chipH);
      ctx.fillStyle = textColor;
      ctx.fillText(labelText, chipX + 6, chipY + 14);
    });
  }, []);

  // ── Draw Plate Bounding Boxes ───────────────────────────────────────────────
  const drawPlateDetections = useCallback((plates: LivePlateDetection[], imageW: number, imageH: number) => {
    const canvas = plateOverlayCanvasRef.current;
    const video = plateVideoRef.current;
    const container = plateContainerRef.current;
    if (!canvas || !video || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const videoW = video.videoWidth || imageW || 640;
    const videoH = video.videoHeight || imageH || 480;
    const videoAspect = videoW / videoH;
    const containerAspect = rect.width / rect.height;

    let renderW = rect.width;
    let renderH = rect.height;
    let offsetX = 0;
    let offsetY = 0;

    if (containerAspect > videoAspect) {
      renderH = rect.height;
      renderW = renderH * videoAspect;
      offsetX = (rect.width - renderW) / 2;
    } else {
      renderW = rect.width;
      renderH = renderW / videoAspect;
      offsetY = (rect.height - renderH) / 2;
    }

    const scaleX = renderW / (imageW || videoW);
    const scaleY = renderH / (imageH || videoH);

    plates.forEach((plate) => {
      if (!plate.box || plate.box.length < 4) return;
      const x = offsetX + plate.box[0] * scaleX;
      const y = offsetY + plate.box[1] * scaleY;
      const w = (plate.box[2] - plate.box[0]) * scaleX;
      const h = (plate.box[3] - plate.box[1]) * scaleY;

      let strokeColor = '#f59e0b';
      let bgChipColor = 'rgba(245, 158, 11, 0.25)';
      let textColor = '#fbbf24';

      if (plate.status === 'registered') {
        strokeColor = '#10b981';
        bgChipColor = 'rgba(16, 185, 129, 0.25)';
        textColor = '#34d399';
      } else if (plate.status === 'flagged') {
        strokeColor = '#f43f5e';
        bgChipColor = 'rgba(244, 63, 94, 0.25)';
        textColor = '#fb7185';
      } else if (plate.status === 'unregistered') {
        strokeColor = '#94a3b8';
        bgChipColor = 'rgba(148, 163, 184, 0.2)';
        textColor = '#cbd5e1';
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 3]);
      ctx.shadowColor = strokeColor;
      ctx.shadowBlur = 8;
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
      ctx.shadowBlur = 0;

      const labelText = plate.label || plate.normalized_plate || 'Plate Detected';
      ctx.font = '700 11px monospace, Inter, sans-serif';
      const textMetrics = ctx.measureText(labelText);
      const chipW = textMetrics.width + 12;
      const chipH = 20;
      const chipX = x;
      const chipY = Math.min(rect.height - chipH - 4, y + h + 4);

      ctx.fillStyle = 'rgba(10, 15, 29, 0.9)';
      ctx.fillRect(chipX, chipY, chipW, chipH);
      ctx.fillStyle = bgChipColor;
      ctx.fillRect(chipX, chipY, chipW, chipH);
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.strokeRect(chipX, chipY, chipW, chipH);
      ctx.fillStyle = textColor;
      ctx.fillText(labelText, chipX + 6, chipY + 14);
    });
  }, []);

  // ── Refresh access attempts and pending reviews without overlapping requests ─
  const refreshPhase3Data = useCallback(async () => {
    if (isPhase3RefreshInFlightRef.current) return;
    isPhase3RefreshInFlightRef.current = true;
    try {
      const [historyRes, reviewsRes] = await Promise.allSettled([
        accessApi.listAttempts({ limit: 30 }),
        accessApi.getPendingReviews(),
      ]);
      if (historyRes.status === 'fulfilled') setAccessHistory(historyRes.value.data);
      else console.warn('Access-attempt refresh failed', historyRes.reason);
      if (reviewsRes.status === 'fulfilled') setPendingReviews(reviewsRes.value.data);
      else console.warn('Pending-review refresh failed', reviewsRes.reason);
    } finally {
      isPhase3RefreshInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    refreshPhase3Data();
    const iv = setInterval(refreshPhase3Data, 7000);
    return () => clearInterval(iv);
  }, [refreshPhase3Data]);

  const refreshWatchlist = useCallback(async () => {
    if (isWatchlistRefreshInFlightRef.current) return;
    isWatchlistRefreshInFlightRef.current = true;
    try {
      const response = await watchlistApi.list({ active_only: true, limit: 50 });
      setWatchlist(response.data);
    } catch (error) {
      console.warn('Watchlist refresh failed', error);
    } finally {
      isWatchlistRefreshInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    refreshWatchlist();
    const interval = setInterval(refreshWatchlist, 20000);
    return () => clearInterval(interval);
  }, [refreshWatchlist]);

  // ── Unified Evaluate Gate Access Function ───────────────────────────────────
  const runEvaluateGateAccess = useCallback(async (targetWfId?: string | null) => {
    setIsSubmittingAttempt(true);
    setAccessError(null);
    isEvaluatingInFlightRef.current = true;
    try {
      const res = await accessApi.createAttempt({
        direction,
        face_verification_id: lastFaceVerIdRef.current ?? undefined,
        alpr_verification_id: lastAlprVerIdRef.current ?? undefined,
      });
      const attempt = res.data;
      setLastDecision(attempt as unknown as AccessAttemptSummary);
      await refreshPhase3Data();

      // Automation State Machine Reconciliation
      if (targetWfId && workflowIdRef.current === targetWfId) {
        resumeCheckpointRef.current = null;
        setResumeCheckpoint(null);

        if (attempt.decision === 'ALLOW') {
          setAutomationState('ACCESS_ALLOWED');
          setAutomationMsg('Access Permitted: Gate barrier opening. Auto-close in 15s.');
        } else if (attempt.decision === 'DENY') {
          setAutomationState('ACCESS_DENIED');
          setAutomationMsg(`Automation stopped — access denied (${attempt.reason_text || 'Policy denial'}). Security officer action required.`);
        } else if (attempt.decision === 'MANUAL_REVIEW') {
          setAutomationState('MANUAL_REVIEW_REQUIRED');
          setAutomationMsg(`Automation paused — security approval required (${attempt.reason_text || 'Manual review queued'}).`);
        }
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const errMsg = e?.response?.data?.detail || e?.message || 'Access decision failed.';
      setAccessError(errMsg);
      if (targetWfId && workflowIdRef.current === targetWfId) {
        resumeCheckpointRef.current = null;
        setResumeCheckpoint(null);
        setAutomationState('ERROR');
        setAutomationMsg(`Access evaluation failed: ${errMsg}`);
      }
    } finally {
      setIsSubmittingAttempt(false);
      isEvaluatingInFlightRef.current = false;
    }
  }, [direction, refreshPhase3Data]);

  // ── Unified Frame Capture & Inference Loop ──────────────────────────────────
  const captureAndProcessFrame = useCallback(async () => {
    // Suspend frame capture and verification when automation is paused
    if (automationStateRef.current === 'PAUSED') {
      return;
    }

    const video = faceVideoRef.current || plateVideoRef.current;
    if (!video || video.readyState < 2 || video.paused || video.ended) {
      return;
    }

    if (isProcessingRef.current) {
      return;
    }

    isProcessingRef.current = true;
    const captureTime = performance.now();
    const frameId = `frame_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

    try {
      const offscreenCanvas = document.createElement('canvas');
      offscreenCanvas.width = video.videoWidth || 640;
      offscreenCanvas.height = video.videoHeight || 480;
      const ctx = offscreenCanvas.getContext('2d');
      if (!ctx) {
        isProcessingRef.current = false;
        return;
      }

      ctx.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);
      const blob = await new Promise<Blob | null>((resolve) =>
        offscreenCanvas.toBlob(resolve, 'image/jpeg', 0.85)
      );

      if (!blob) {
        isProcessingRef.current = false;
        return;
      }

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      const response = await aiApi.processLiveFrame(blob, frameId, captureTime, abortController.signal);

      // Guard: if workflow paused or cancelled while network request was in-flight, discard response
      const latestState = automationStateRef.current as unknown as AutomationState;
      if (latestState === 'PAUSED' || latestState === 'CANCELLED') {
        return;
      }

      const data = response.data;

      setLastTiming({
        total: data.timing.total_latency_ms,
        face: data.timing.face_latency_ms,
        plate: data.timing.plate_latency_ms,
      });
      setCurrentFaces(data.faces);
      setCurrentPlates(data.plates);

      if (data.storage) {
        setLastSavedStorage(data.storage);
      }
      if (data.face_verification_id) {
        lastFaceVerIdRef.current = data.face_verification_id;
      }
      if (data.alpr_verification_id) {
        lastAlprVerIdRef.current = data.alpr_verification_id;
      }

      drawFaceDetections(data.faces, data.image_width, data.image_height);
      drawPlateDetections(data.plates, data.image_width, data.image_height);

      frameCountRef.current += 1;
      const now = performance.now();
      const deltaSec = (now - lastFpsCalcTimeRef.current) / 1000;
      if (deltaSec >= 1.0) {
        setFps(Math.round((frameCountRef.current / deltaSec) * 10) / 10);
        frameCountRef.current = 0;
        lastFpsCalcTimeRef.current = now;
      }

      // ── 1. FACE STAGE LOGIC (Manual & Automated) ────────────────────────────
      if (faceStageState === 'SCANNING' || faceStageState === 'FACE_DETECTED' || faceStageState === 'VERIFYING' || faceStageState === 'FAILED') {
        if (data.faces.length === 0) {
          setFaceStageState('SCANNING');
          setFaceGuidance('Position your face within the camera view.');
        } else if (data.faces.length > 1) {
          setFaceStageState('FACE_DETECTED');
          setFaceGuidance('Ensure only the intended person is in the verification area.');
        } else {
          const f = data.faces[0];
          setFaceStageState('VERIFYING');

          if (f.status === 'matched') {
            setFaceStageState('VERIFIED');
            setVerifiedFace(f);
            setFaceGuidance('Identity verified. Proceeding to vehicle verification...');

            // Automated Stage Transition to Number Plate
            if (automationStateRef.current === 'FACE_VERIFICATION') {
              const currentWf = workflowIdRef.current;
              setAutomationState('FACE_VERIFIED');
              setAutomationMsg(`Identity verified (${f.person?.name || 'Matched'}). Automatically advancing to plate recognition...`);

              setTimeout(() => {
                if (workflowIdRef.current !== currentWf || automationStateRef.current !== 'FACE_VERIFIED') return;
                setPlateStageState('SCANNING');
                setPlateGuidance('Move the vehicle into the camera view.');
                setAutomationState('PLATE_VERIFICATION');
                setAutomationMsg('Recognizing number plate: Move vehicle into camera view...');
              }, 400);
            }
          } else if (f.status === 'unknown' || f.status === 'low_confidence') {
            const nowMs = Date.now();
            if (nowMs - lastFailedAttemptTimeRef.current > 3000) {
              lastFailedAttemptTimeRef.current = nowMs;
              const nextCount = failedAttemptsCountRef.current + 1;
              failedAttemptsCountRef.current = nextCount;
              setFailedFaceAttempts(nextCount);

              if (nextCount >= 3) {
                setFaceStageState('MAX_ATTEMPTS_REACHED');
                setFaceGuidance('Maximum 3 attempts reached. Identity could not be verified. Operator manual review required.');
                if (automationStateRef.current === 'FACE_VERIFICATION') {
                  setAutomationState('ERROR');
                  setAutomationMsg('Automation stopped: Maximum 3 failed face attempts reached. Manual review required.');
                }
              } else {
                setFaceStageState('FAILED');
                setFaceGuidance(`Identity could not be verified (Attempt ${nextCount}/3). Move closer and ensure adequate lighting.`);
              }
            } else {
              setFaceGuidance('Hold still while we verify your identity...');
            }
          }
        }
      }

      // ── 2. PLATE STAGE LOGIC (Manual & Automated) ───────────────────────────
      if (plateStageState === 'SCANNING' || plateStageState === 'PLATE_DETECTED') {
        if (data.plates.length === 0) {
          setPlateGuidance('Move the vehicle into the camera view.');
        } else {
          const p = data.plates[0];
          setVerifiedPlate(p);

          const handlePlateSuccessInAutomation = (detectedPlate: LivePlateDetection) => {
            if (automationStateRef.current === 'PLATE_VERIFICATION' && !hasEvaluatedRef.current) {
              hasEvaluatedRef.current = true;
              const currentWf = workflowIdRef.current;
              setAutomationState('PLATE_VERIFIED');
              setAutomationMsg(`Number plate detected (${detectedPlate.normalized_plate || detectedPlate.label || 'OCR'}). Evaluating gate access...`);

              setTimeout(async () => {
                if (workflowIdRef.current !== currentWf || automationStateRef.current !== 'PLATE_VERIFIED') return;
                setAutomationState('EVALUATING_ACCESS');
                setAutomationMsg('Evaluating access decision with campus security engine...');
                await runEvaluateGateAccess(currentWf);
              }, 500);
            }
          };

          if (p.status === 'registered') {
            setPlateStageState('REGISTERED');
            setPlateGuidance('Registered vehicle identified. Evaluating gate access...');
            handlePlateSuccessInAutomation(p);
          } else if (p.status === 'flagged') {
            setPlateStageState('FLAGGED');
            setPlateGuidance('Warning: Vehicle is flagged on security watchlist. Evaluating access...');
            handlePlateSuccessInAutomation(p);
          } else if (p.status === 'unregistered') {
            setPlateStageState('UNREGISTERED');
            setPlateGuidance('No registered vehicle matches this plate. Evaluating access...');
            handlePlateSuccessInAutomation(p);
          } else {
            setPlateStageState('PLATE_DETECTED');
            setPlateGuidance('Number plate detected. Checking campus records...');
          }
        }
      }

      // Deduplicated detection history feed
      const nowTimestamp = Date.now();
      const COOLDOWN_MS = 8000;
      const newItems: DetectionHistoryItem[] = [];

      data.faces.forEach((f) => {
        const key = f.person?.id ? `person_${f.person.id}` : f.status === 'matched' ? `matched_${f.label}` : null;
        if (key) {
          const lastSeen = cooldownMapRef.current.get(key) || 0;
          if (nowTimestamp - lastSeen > COOLDOWN_MS) {
            cooldownMapRef.current.set(key, nowTimestamp);
            newItems.push({
              id: `${key}_${nowTimestamp}`,
              type: 'face',
              label: f.person?.name || f.label,
              subLabel: f.person?.person_type ? `Type: ${f.person.person_type}` : `Score: ${f.score?.toFixed(2) ?? 'N/A'}`,
              timestamp: new Date(),
              status: f.status,
              score: f.score,
            });
          }
        }
      });

      data.plates.forEach((p) => {
        if (p.normalized_plate) {
          const key = `plate_${p.normalized_plate}`;
          const lastSeen = cooldownMapRef.current.get(key) || 0;
          if (nowTimestamp - lastSeen > COOLDOWN_MS) {
            cooldownMapRef.current.set(key, nowTimestamp);
            newItems.push({
              id: `${key}_${nowTimestamp}`,
              type: 'plate',
              label: p.normalized_plate,
              subLabel: p.vehicle?.owner_name ? `Owner: ${p.vehicle.owner_name}` : p.status,
              timestamp: new Date(),
              status: p.status,
              score: p.ocr_confidence,
            });
          }
        }
      });

      if (newItems.length > 0) {
        setHistory((prev) => [...newItems, ...prev].slice(0, 20));
      }
    } catch (err: unknown) {
      const isCanceled = (err as { code?: string; name?: string })?.name === 'CanceledError' || (err as { code?: string })?.code === 'ERR_CANCELED';
      if (!isCanceled) {
        console.warn('Live frame processing error:', err);
      }
    } finally {
      isProcessingRef.current = false;
      abortControllerRef.current = null;
    }
  }, [drawFaceDetections, drawPlateDetections, faceStageState, plateStageState, runEvaluateGateAccess]);

  // ── Stop Camera Stream ──────────────────────────────────────────────────────
  const stopCamera = useCallback(() => {
    if (intervalTimerRef.current) {
      clearInterval(intervalTimerRef.current);
      intervalTimerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (faceVideoRef.current) faceVideoRef.current.srcObject = null;
    if (plateVideoRef.current) plateVideoRef.current.srcObject = null;

    isProcessingRef.current = false;
    setCameraStatus('idle');
    setFps(0);
    clearOverlays();
  }, [clearOverlays]);

  // ── Start Camera Stream & Bind to Previews ──────────────────────────────────
  const startCamera = useCallback(async () => {
    stopCamera();
    setCameraStatus('starting');
    setCameraError(null);

    try {
      const constraints: MediaStreamConstraints = {
        video: selectedDeviceId
          ? { deviceId: { exact: selectedDeviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
          : { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        audio: false,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      if (faceVideoRef.current) {
        faceVideoRef.current.srcObject = stream;
        faceVideoRef.current.onloadedmetadata = () => {
          faceVideoRef.current?.play().catch(console.warn);
        };
      }
      if (plateVideoRef.current) {
        plateVideoRef.current.srcObject = stream;
        plateVideoRef.current.onloadedmetadata = () => {
          plateVideoRef.current?.play().catch(console.warn);
        };
      }

      setCameraStatus('live');
      refreshDevices();

      if (intervalTimerRef.current) {
        clearInterval(intervalTimerRef.current);
      }
      intervalTimerRef.current = setInterval(captureAndProcessFrame, captureIntervalMs);
    } catch (err: unknown) {
      console.error('Camera initialization failed:', err);
      const errorName = (err as { name?: string })?.name;
      if (errorName === 'NotAllowedError' || errorName === 'PermissionDeniedError') {
        setCameraStatus('permission_denied');
        setCameraError('Camera access was denied by browser. Please allow camera permissions in your browser URL bar.');
        setFaceGuidance('Camera access is unavailable. Check permissions and try again.');
        setPlateGuidance('Camera access is unavailable. Check permissions and try again.');
      } else if (errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError') {
        setCameraStatus('unavailable');
        setCameraError('No video camera device was found on this system.');
      } else {
        setCameraStatus('unavailable');
        setCameraError((err as Error)?.message || 'Failed to initialize camera device.');
      }
    }
  }, [selectedDeviceId, captureIntervalMs, captureAndProcessFrame, refreshDevices, stopCamera]);

  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
    };
  }, []);

  useEffect(() => {
    if (cameraStatus === 'live') {
      if (intervalTimerRef.current) {
        clearInterval(intervalTimerRef.current);
      }
      intervalTimerRef.current = setInterval(captureAndProcessFrame, captureIntervalMs);
    }
    return () => {
      if (intervalTimerRef.current) {
        clearInterval(intervalTimerRef.current);
      }
    };
  }, [captureIntervalMs, cameraStatus, captureAndProcessFrame]);

  // ── Manual Evidence Snapshot ───────────────────────────────────────────────
  const takeSnapshot = useCallback(async () => {
    const video = faceVideoRef.current || plateVideoRef.current;
    if (!video || cameraStatus !== 'live') return;
    setIsSavingSnapshot(true);
    setSnapshotMsg(null);
    try {
      const offscreen = document.createElement('canvas');
      offscreen.width = video.videoWidth || 640;
      offscreen.height = video.videoHeight || 480;
      const ctx = offscreen.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, offscreen.width, offscreen.height);
      const blob = await new Promise<Blob | null>((resolve) =>
        offscreen.toBlob(resolve, 'image/jpeg', 0.9)
      );
      if (!blob) return;
      const res = await aiApi.saveSnapshot(blob, `Manual Gate Terminal capture (${direction})`);
      setLastSavedStorage(res.data);
      if (res.data.remote_ok) {
        setSnapshotMsg('Evidence saved to Supabase Storage ✓');
      } else if (res.data.local_ok) {
        setSnapshotMsg('Evidence saved to local disk ✓');
      }
      setTimeout(() => setSnapshotMsg(null), 4000);
    } catch (err) {
      console.warn('Snapshot capture failed:', err);
      setSnapshotMsg('Failed to save snapshot');
      setTimeout(() => setSnapshotMsg(null), 3000);
    } finally {
      setIsSavingSnapshot(false);
    }
  }, [cameraStatus, direction]);

  // ── Reset Entire Workflow ───────────────────────────────────────────────────
  const resetWorkflow = useCallback(() => {
    workflowIdRef.current = null;
    resumeCheckpointRef.current = null;
    setResumeCheckpoint(null);
    hasEvaluatedRef.current = false;
    setAutomationState('IDLE');
    setAutomationMsg('Ready: Click "Start Automation" to automatically verify face, recognize vehicle, and evaluate gate access.');

    setFaceStageState('NOT_STARTED');
    setFailedFaceAttempts(0);
    failedAttemptsCountRef.current = 0;
    lastFailedAttemptTimeRef.current = 0;
    setVerifiedFace(null);
    setFaceGuidance('Click "Start Face Verification" or "Start Automation" to begin scanning.');

    setPlateStageState('NOT_STARTED');
    setVerifiedPlate(null);
    setPlateGuidance('Click "Start Plate Verification" when vehicle is positioned.');

    lastFaceVerIdRef.current = null;
    lastAlprVerIdRef.current = null;
    setLastDecision(null);
    setAccessError(null);
    clearOverlays();
  }, [clearOverlays]);

  // ── Automated Workflow Controller ───────────────────────────────────────────
  const isAutomationRunning =
    automationState !== 'IDLE' &&
    automationState !== 'PAUSED' &&
    automationState !== 'ACCESS_ALLOWED' &&
    automationState !== 'ACCESS_DENIED' &&
    automationState !== 'MANUAL_REVIEW_REQUIRED' &&
    automationState !== 'ERROR' &&
    automationState !== 'CANCELLED';

  const isAutomationPaused = automationState === 'PAUSED';
  const isAutomationActive = isAutomationRunning || isAutomationPaused;

  const startAutomation = async () => {
    const newWfId = `wf_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    workflowIdRef.current = newWfId;
    resumeCheckpointRef.current = null;
    setResumeCheckpoint(null);
    hasEvaluatedRef.current = false;

    // Reset workflow state for genuinely new attempt
    setVerifiedFace(null);
    setVerifiedPlate(null);
    lastFaceVerIdRef.current = null;
    lastAlprVerIdRef.current = null;
    setLastDecision(null);
    setAccessError(null);
    setFailedFaceAttempts(0);
    failedAttemptsCountRef.current = 0;
    lastFailedAttemptTimeRef.current = 0;
    clearOverlays();

    setAutomationState('INITIALIZING_CAMERA');
    setAutomationMsg('Checking camera stream availability...');

    if (cameraStatus !== 'live') {
      try {
        await startCamera();
        await new Promise((r) => setTimeout(r, 400));
      } catch (_) {
        if (workflowIdRef.current !== newWfId) return;
        setAutomationState('ERROR');
        setAutomationMsg('Camera unavailable. Check permissions and try again.');
        return;
      }
    }

    if (workflowIdRef.current !== newWfId) return;

    // Launch Stage 1: Face Verification
    setFaceStageState('SCANNING');
    setPlateStageState('NOT_STARTED');
    setFaceGuidance('Position your face within the camera view.');
    setAutomationState('FACE_VERIFICATION');
    setAutomationMsg('Stage 1 active: Hold still while identity is verified...');
  };

  const pauseAutomation = useCallback((reasonMsg?: string) => {
    // Idempotent: only pause if actively running
    if (!isAutomationRunning || automationStateRef.current === 'PAUSED') return;

    // Determine safe resume checkpoint
    let cp: ResumeCheckpoint = 'FACE_VERIFICATION';
    const cur = automationStateRef.current;
    if (cur === 'FACE_VERIFICATION' || cur === 'INITIALIZING_CAMERA') {
      cp = 'FACE_VERIFICATION';
    } else if (cur === 'FACE_VERIFIED') {
      cp = 'FACE_VERIFIED';
    } else if (cur === 'PLATE_VERIFICATION') {
      cp = 'PLATE_VERIFICATION';
    } else if (cur === 'PLATE_VERIFIED') {
      cp = 'PLATE_VERIFIED';
    } else if (cur === 'EVALUATING_ACCESS') {
      cp = 'EVALUATING_ACCESS';
    }

    resumeCheckpointRef.current = cp;
    setResumeCheckpoint(cp);
    automationStateRef.current = 'PAUSED';
    setAutomationState('PAUSED');
    setAutomationMsg(reasonMsg || 'Automation is paused. Verification will not proceed until you resume.');

    // Abort active frame sampling if in-flight
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, [isAutomationRunning]);

  const resumeAutomation = useCallback(async () => {
    // 1. Confirm workflow not cancelled, resolved, or superseded (idempotent)
    if (!workflowIdRef.current || automationStateRef.current !== 'PAUSED') {
      return;
    }

    // 2. Confirm officer remains authorized
    if (!user) {
      setAutomationState('ERROR');
      setAutomationMsg('Unauthorized session. Please log in again to resume automation.');
      return;
    }

    const currentWf = workflowIdRef.current;
    const cp = resumeCheckpointRef.current || 'FACE_VERIFICATION';

    // 3. Check whether camera is still available; restore if needed
    if (cameraStatus !== 'live' || !streamRef.current) {
      setAutomationState('INITIALIZING_CAMERA');
      setAutomationMsg('Restoring camera stream before resuming...');
      try {
        await startCamera();
        await new Promise((r) => setTimeout(r, 400));
        if (workflowIdRef.current !== currentWf) return;
      } catch (_) {
        if (workflowIdRef.current !== currentWf) return;
        setAutomationState('ERROR');
        setAutomationMsg('Camera unavailable. Check permissions and try again.');
        return;
      }
    }

    if (workflowIdRef.current !== currentWf) return;

    // 4. Resume from current safe checkpoint without duplicate execution
    resumeCheckpointRef.current = null;
    setResumeCheckpoint(null);

    if (cp === 'FACE_VERIFICATION') {
      setFaceStageState('SCANNING');
      setFaceGuidance('Resumed: Position your face within the camera view.');
      setAutomationState('FACE_VERIFICATION');
      setAutomationMsg('Stage 1 active (resumed): Hold still while identity is verified...');
    } else if (cp === 'FACE_VERIFIED') {
      if (verifiedFace) {
        setPlateStageState('SCANNING');
        setPlateGuidance('Resumed: Move vehicle into camera view.');
        setAutomationState('PLATE_VERIFICATION');
        setAutomationMsg('Stage 2 active (resumed): Recognizing number plate: Move vehicle into camera view...');
      } else {
        setFaceStageState('SCANNING');
        setFaceGuidance('Identity verification expired. Position face within camera view.');
        setAutomationState('FACE_VERIFICATION');
        setAutomationMsg('Resumed: Face verification expired. Restarting Stage 1...');
      }
    } else if (cp === 'PLATE_VERIFICATION') {
      setPlateStageState('SCANNING');
      setPlateGuidance('Resumed: Move vehicle into camera view.');
      setAutomationState('PLATE_VERIFICATION');
      setAutomationMsg('Stage 2 active (resumed): Move vehicle into camera view...');
    } else if (cp === 'PLATE_VERIFIED' || cp === 'EVALUATING_ACCESS') {
      if (verifiedPlate && lastFaceVerIdRef.current) {
        setAutomationState('EVALUATING_ACCESS');
        setAutomationMsg('Resumed: Evaluating access decision with campus security engine...');
        hasEvaluatedRef.current = true;
        await runEvaluateGateAccess(currentWf);
      } else if (!lastFaceVerIdRef.current) {
        setFaceStageState('SCANNING');
        setFaceGuidance('Identity verification expired. Position face within camera view.');
        setAutomationState('FACE_VERIFICATION');
        setAutomationMsg('Resumed: Identity evidence missing. Restarting Stage 1...');
      } else {
        setPlateStageState('SCANNING');
        setPlateGuidance('Resumed: Move vehicle into camera view.');
        setAutomationState('PLATE_VERIFICATION');
        setAutomationMsg('Resumed: Plate evidence missing. Re-scanning plate...');
      }
    }
  }, [cameraStatus, startCamera, user, verifiedFace, verifiedPlate, runEvaluateGateAccess]);

  const stopAutomation = useCallback(() => {
    workflowIdRef.current = null;
    resumeCheckpointRef.current = null;
    setResumeCheckpoint(null);
    hasEvaluatedRef.current = false;
    setAutomationState('CANCELLED');
    setAutomationMsg('Automation cancelled by security officer.');
    setFaceStageState('CANCELLED');
    setPlateStageState('CANCELLED');
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Monitor camera status during automation and auto-pause on disconnect
  useEffect(() => {
    if (
      (cameraStatus === 'unavailable' || cameraStatus === 'permission_denied') &&
      isAutomationRunning
    ) {
      pauseAutomation('Camera stream disconnected. Automation paused for safety.');
    }
  }, [cameraStatus, isAutomationRunning, pauseAutomation]);

  // ── Direction Change Guard ──────────────────────────────────────────────────
  const handleDirectionClick = (newDir: Direction) => {
    if (newDir === direction) return;
    const isWorkflowActive =
      isAutomationActive ||
      faceStageState !== 'NOT_STARTED' ||
      plateStageState !== 'NOT_STARTED' ||
      verifiedFace !== null ||
      verifiedPlate !== null ||
      failedFaceAttempts > 0;

    if (isWorkflowActive) {
      setPendingDirectionChange(newDir);
    } else {
      setDirection(newDir);
    }
  };

  const confirmDirectionChange = () => {
    if (pendingDirectionChange) {
      setDirection(pendingDirectionChange);
      setPendingDirectionChange(null);
      resetWorkflow();
    }
  };

  // ── Stage Control Actions ───────────────────────────────────────────────────
  const startFaceVerification = () => {
    if (isAutomationActive) return;
    if (faceStageState === 'MAX_ATTEMPTS_REACHED') {
      setFailedFaceAttempts(0);
      failedAttemptsCountRef.current = 0;
      lastFailedAttemptTimeRef.current = 0;
    }
    setFaceStageState('SCANNING');
    setFaceGuidance('Position your face within the camera view.');
  };

  const stopFaceVerification = () => {
    if (isAutomationActive) {
      stopAutomation();
      return;
    }
    setFaceStageState('CANCELLED');
    setFaceGuidance('Face verification stopped by officer.');
  };

  const startPlateVerification = () => {
    if (isAutomationActive) return;
    setPlateStageState('SCANNING');
    setPlateGuidance('Move the vehicle into the camera view.');
  };

  const stopPlateVerification = () => {
    if (isAutomationActive) {
      stopAutomation();
      return;
    }
    setPlateStageState('CANCELLED');
    setPlateGuidance('Plate verification stopped by officer.');
  };

  const evaluateGateAccess = useCallback(async () => {
    if (isAutomationActive) return;
    await runEvaluateGateAccess(null);
  }, [isAutomationActive, runEvaluateGateAccess]);

  // ── Resolve Officer Manual Review ───────────────────────────────────────────
  const resolveReview = useCallback(async (id: string, resolution: 'approved' | 'denied') => {
    if (!reviewNote.trim() && resolution === 'denied') {
      setAccessError('A clearance note or reason is required to deny access.');
      return;
    }
    const note = reviewNote.trim() || (resolution === 'approved' ? 'Officer verified at gate.' : 'Officer denied at gate.');
    setIsResolvingReview(true);
    try {
      await accessApi.resolveReview(id, { resolution, reason: note });
      setReviewingId(null);
      setReviewNote('');
      await refreshPhase3Data();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setAccessError(e?.response?.data?.detail || 'Resolution failed.');
    } finally {
      setIsResolvingReview(false);
    }
  }, [reviewNote, refreshPhase3Data]);

  // ── Manual Gate Reset ───────────────────────────────────────────────────────
  const handleResetGate = useCallback(async () => {
    try {
      const res = await gateApi.reset();
      setGateStatus(res.data.status);
      const hardware = res.data.hardware;
      setGateFeedback(hardware.acknowledged
        ? 'Controller acknowledged the reset close command; gate position is not sensor-verified.'
        : hardware.delivered && hardware.status === 'REJECTED'
        ? res.data.message
        : hardware.delivered
        ? `Reset close command delivered; controller acknowledgement unavailable (${hardware.error || 'timeout'}).`
        : `Close command failed; gate state was not changed (${hardware.error || 'service unavailable'}).`);
      await refreshPhase3Data();
    } catch (err: unknown) {
      setGateFeedback(`Failed to reset gate: ${err instanceof Error ? err.message : 'Unknown error'}`);
      console.warn('Failed to reset gate:', err);
    }
  }, [refreshPhase3Data]);

  // ── Issue Temporary Visitor Pass ───────────────────────────────────────────
  const [isIssuingVisitor, setIsIssuingVisitor] = useState(false);
  const handleIssueVisitorPass = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!visitorName.trim()) return;
    try {
      setIsIssuingVisitor(true);
      const now = new Date();
      const validUntil = new Date(now.getTime() + 8 * 60 * 60 * 1000);
      const pass = await visitorsApi.registerVisitor({
        full_name: visitorName.trim(),
        vehicle_plate: visitorPlate.trim() || undefined,
        purpose: visitorPurpose,
        valid_from: now.toISOString(),
        valid_until: validUntil.toISOString(),
        send_email: false,
      });
      setVisitorSuccessMsg(`Pass ${pass.pass_number} issued for ${visitorName} (Vehicle: ${visitorPlate || 'Pedestrian'}). Checkpoint QR pass is ready.`);
      setTimeout(() => {
        setVisitorSuccessMsg(null);
        setIsVisitorModalOpen(false);
        setVisitorName('');
        setVisitorPlate('');
        setVisitorHost('');
      }, 3000);
    } catch (err: unknown) {
      console.error('Failed to issue visitor pass', err);
      setVisitorSuccessMsg('Error issuing pass. Please use the complete Visitor Management portal.');
    } finally {
      setIsIssuingVisitor(false);
    }
  };

  // ── Derived Summaries ───────────────────────────────────────────────────────
  const isLive = cameraStatus === 'live';
  const faceReady = diagnostics?.recommendation.face_recognition_ready ?? true;
  const alprReady = diagnostics?.recommendation.alpr_ready ?? true;

  const getIdentityMatchStatus = () => {
    if (faceStageState === 'VERIFIED') return { text: 'Matched', variant: 'success' as const };
    if (faceStageState === 'MAX_ATTEMPTS_REACHED') return { text: 'Manual review required', variant: 'warning' as const };
    if (faceStageState === 'FAILED') return { text: 'Not matched', variant: 'error' as const };
    if (faceStageState === 'SCANNING' || faceStageState === 'FACE_DETECTED' || faceStageState === 'VERIFYING')
      return { text: 'Verifying', variant: 'neutral' as const };
    if (faceStageState === 'ERROR') return { text: 'Error', variant: 'error' as const };
    return { text: 'Pending', variant: 'neutral' as const };
  };

  const getVehicleMatchStatus = () => {
    if (plateStageState === 'FLAGGED') return { text: 'Flagged vehicle', variant: 'error' as const };
    if (plateStageState === 'UNREGISTERED') return { text: 'Unregistered vehicle', variant: 'warning' as const };
    if (plateStageState === 'REGISTERED') {
      if (verifiedFace?.person?.id && verifiedPlate?.vehicle?.owner_person_id) {
        if (verifiedFace.person.id === verifiedPlate.vehicle.owner_person_id) {
          return { text: 'Owner matched', variant: 'success' as const };
        } else {
          return { text: 'Owner mismatch', variant: 'warning' as const };
        }
      }
      return { text: 'Registered', variant: 'success' as const };
    }
    if (plateStageState === 'SCANNING' || plateStageState === 'PLATE_DETECTED')
      return { text: 'Verifying', variant: 'neutral' as const };
    if (plateStageState === 'ERROR') return { text: 'Error', variant: 'error' as const };
    return { text: 'Pending', variant: 'neutral' as const };
  };

  const getDecisionStatus = () => {
    if (isSubmittingAttempt) return { text: 'Evaluating...', variant: 'neutral' as const };
    if (lastDecision?.decision === 'ALLOW') return { text: 'ALLOW', variant: 'success' as const };
    if (lastDecision?.decision === 'DENY') return { text: 'DENY', variant: 'error' as const };
    if (lastDecision?.decision === 'MANUAL_REVIEW') return { text: 'MANUAL_REVIEW', variant: 'warning' as const };
    return { text: 'Pending', variant: 'neutral' as const };
  };

  const identityStatus = getIdentityMatchStatus();
  const vehicleStatus = getVehicleMatchStatus();
  const decisionStatus = getDecisionStatus();

  return (
    <div className="space-y-6">
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* PAGE HEADER WITH OPERATOR DETAILS & AI LAB LINK                     */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <PageHeader
        title="Security Terminal — Gate 1 Operations"
        description="Autonomous fail-closed gate control with live facial recognition, vehicle ALPR OCR, and campus security policy evaluation."
        badge={
          <StatusBadge variant={isLive ? 'success' : 'neutral'} size="sm" pulse={isLive}>
            {isLive ? 'TERMINAL ACTIVE' : 'CAMERA OFFLINE'}
          </StatusBadge>
        }
        action={
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              Officer: <strong className="text-slate-200">@{user?.username || 'officer'}</strong>
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate('/security/alerts')}
              leftIcon={<ShieldAlert className="w-3.5 h-3.5 text-amber-400" />}
            >
              Alert Center
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate('/security/ai-lab')}
              leftIcon={<Activity className="w-3.5 h-3.5" />}
            >
              AI Lab
            </Button>
          </div>
        }
      />

      <CampusEntryOverview />

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* CAMERA HARDWARE & TELEMETRY CONTROL BAR                            */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <Card className="p-3.5 border-white/[0.08] bg-[#0E1322]">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {isLive ? (
              <Button
                variant="danger"
                size="sm"
                onClick={stopCamera}
                leftIcon={<Square className="w-3.5 h-3.5" />}
              >
                Stop Camera
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={startCamera}
                isLoading={cameraStatus === 'starting'}
                leftIcon={<Play className="w-3.5 h-3.5" />}
              >
                Start Camera
              </Button>
            )}

            {videoDevices.length > 0 && (
              <div className="relative">
                <select
                  value={selectedDeviceId}
                  onChange={(e) => {
                    setSelectedDeviceId(e.target.value);
                    if (isLive) {
                      setTimeout(startCamera, 100);
                    }
                  }}
                  className="appearance-none bg-[#0B101D] border border-white/[0.1] rounded-lg px-3 py-1.5 pr-8 text-xs text-slate-200 focus:outline-none focus:border-[#7565F5]"
                >
                  {videoDevices.map((d, idx) => (
                    <option key={d.deviceId || idx} value={d.deviceId}>
                      {d.label || `Camera ${idx + 1}`}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            )}

            <Button
              variant="ghost"
              size="sm"
              onClick={refreshDevices}
              title="Refresh camera devices"
              leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
            >
              Refresh
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={takeSnapshot}
              disabled={!isLive || isSavingSnapshot}
              isLoading={isSavingSnapshot}
              leftIcon={<Camera className="w-3.5 h-3.5" />}
            >
              Take Snapshot
            </Button>

            {snapshotMsg && (
              <span className="text-xs text-emerald-400 font-medium flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {snapshotMsg}
              </span>
            )}

            {lastSavedStorage && (
              <span className="text-[11px] text-slate-400 flex items-center gap-2">
                {lastSavedStorage.remote_ok ? (
                  <span className="flex items-center gap-1 text-cyan-400">
                    <Cloud className="w-3.5 h-3.5" /> Supabase Storage ✓
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-amber-400">
                    <HardDrive className="w-3.5 h-3.5" /> Local Disk ✓
                  </span>
                )}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <div className="flex items-center gap-2 font-mono">
              <span className="bg-[#0B101D] border border-white/[0.08] px-2 py-0.5 rounded text-slate-300">
                {fps} FPS
              </span>
              {lastTiming && (
                <span className="bg-[#0B101D] border border-white/[0.08] px-2 py-0.5 rounded text-indigo-300">
                  {lastTiming.total}ms
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-slate-400" />
              <span>Interval:</span>
              <div className="flex items-center gap-1 bg-[#0B101D] border border-white/[0.08] rounded-lg p-0.5">
                {[500, 750, 1000].map((ms) => (
                  <button
                    key={ms}
                    onClick={() => setCaptureIntervalMs(ms)}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                      captureIntervalMs === ms
                        ? 'bg-[#7565F5] text-white shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {ms}ms
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* USER ENTRY MANAGEMENT HEADER & DIRECTION SEGMENTED CONTROL          */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-[#0E1322] border border-white/[0.08] shadow-xl">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#7565F5]/10 border border-[#7565F5]/25 flex items-center justify-center text-[#9B8DFC] shadow-inner">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              <span>USER ENTRY MANAGEMENT</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.06] text-slate-300 border border-white/[0.08]">
                GATE 1 TERMINAL
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              Guided optical identity recognition, license plate OCR, and fail-closed automated gate authorization.
            </p>
          </div>
        </div>

        {/* Direction Segmented Control */}
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-[#070B14] border border-white/[0.1] rounded-xl p-1 gap-1">
            <button
              onClick={() => handleDirectionClick('ENTRY')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold tracking-wide transition-all ${
                direction === 'ENTRY'
                  ? 'bg-gradient-to-r from-[#7565F5] to-[#6353E8] text-white shadow-lg shadow-[#7565F5]/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ArrowDownCircle className="w-4 h-4 text-emerald-400" />
              <span>ENTRY</span>
            </button>
            <button
              onClick={() => handleDirectionClick('EXIT')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold tracking-wide transition-all ${
                direction === 'EXIT'
                  ? 'bg-gradient-to-r from-[#7565F5] to-[#6353E8] text-white shadow-lg shadow-[#7565F5]/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ArrowUpCircle className="w-4 h-4 text-amber-400" />
              <span>EXIT</span>
            </button>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={resetWorkflow}
            title="Reset current verification workflow"
            leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
          >
            Reset
          </Button>

          {/* Gate command controls */}
          <div className="flex items-center bg-[#070B14] border border-white/[0.1] rounded-xl p-1 gap-1.5 shadow-lg">
            <div className="px-2.5 py-1 text-[11px] font-mono flex items-center gap-1.5">
              <span className="text-slate-400 font-sans font-semibold">SOFTWARE GATE:</span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                  (gateStatus?.state === 'OPEN' || gateStatus?.state === 'MANUAL_LATCHED_OPEN')
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse'
                    : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                }`}
              >
                {gateStatus?.state || 'CLOSED'}
              </span>
            </div>
            <div className="px-2.5 py-1 text-[11px] font-mono flex items-center gap-1.5" aria-live="polite">
              <span className="text-slate-400 font-sans font-semibold">ESP32:</span>
              <span className="text-slate-200">
                {gateStatus?.iot_controller?.reported_gate_state || 'UNKNOWN'}
              </span>
              {gateStatus?.iot_controller?.reported_gate_mode === 'MANUAL_LATCHED_OPEN' && (
                <span className="text-emerald-300 font-bold">MANUAL LATCHED</span>
              )}
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleManualOpenGate}
              disabled={isGateOperating}
              leftIcon={<Unlock className="w-3.5 h-3.5 text-emerald-400" />}
              className="bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border-emerald-500/30 text-xs font-bold"
              title="Manually command ESP32 gate to open"
            >
              Manual Open
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleManualCloseGate}
              disabled={isGateOperating}
              leftIcon={<Lock className="w-3.5 h-3.5 text-rose-400" />}
              className="bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border-rose-500/30 text-xs font-bold"
              title="Manually command ESP32 gate to close"
            >
              Manual Close
            </Button>
          </div>
        </div>
      </div>

      {/* Gate Command Feedback Toast */}
      {gateFeedback && (
        <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>{gateFeedback}</span>
          </div>
          <button onClick={() => setGateFeedback(null)} className="p-1 hover:bg-cyan-500/20 rounded">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Confirmation Modal: Changing Direction During Active Workflow */}
      {pendingDirectionChange && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <Card className="max-w-md w-full p-5 border-amber-500/30 bg-[#0E1322] space-y-4">
            <div className="flex items-center gap-3 text-amber-400">
              <AlertTriangle className="w-6 h-6 shrink-0" />
              <h3 className="text-sm font-bold text-slate-100">Confirm Direction Change</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              An active verification is currently in progress. Changing access direction to{' '}
              <strong className="text-white font-mono">{pendingDirectionChange}</strong> will cancel the ongoing verification
              and reset all face and plate results.
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPendingDirectionChange(null)}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={confirmDirectionChange}
                leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              >
                Reset & Change to {pendingDirectionChange}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Navigation Tabs: Workflow vs Secondary Panels */}
      <div className="flex items-center gap-2 border-b border-white/[0.08] pb-1 text-xs">
        <button
          onClick={() => setActiveTab('terminal')}
          className={`flex items-center gap-2 px-3.5 py-2 font-semibold rounded-t-lg transition-colors ${
            activeTab === 'terminal'
              ? 'text-white border-b-2 border-[#7565F5] bg-white/[0.04]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Shield className="w-3.5 h-3.5 text-[#7565F5]" />
          <span>Entry Workflow</span>
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`flex items-center gap-2 px-3.5 py-2 font-semibold rounded-t-lg transition-colors ${
            activeTab === 'audit'
              ? 'text-white border-b-2 border-[#7565F5] bg-white/[0.04]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <ClipboardList className="w-3.5 h-3.5 text-indigo-400" />
          <span>Audit Trail ({accessHistory.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('watchlist')}
          className={`flex items-center gap-2 px-3.5 py-2 font-semibold rounded-t-lg transition-colors ${
            activeTab === 'watchlist'
              ? 'text-white border-b-2 border-[#7565F5] bg-white/[0.04]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <List className="w-3.5 h-3.5 text-rose-400" />
          <span>Active Watchlist ({watchlist.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('schedule')}
          className={`flex items-center gap-2 px-3.5 py-2 font-semibold rounded-t-lg transition-colors ${
            activeTab === 'schedule'
              ? 'text-white border-b-2 border-[#7565F5] bg-white/[0.04]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Calendar className="w-3.5 h-3.5 text-emerald-400" />
          <span>Campus Schedule</span>
        </button>

        <button
          onClick={() => setActiveTab('diagnostics')}
          className={`flex items-center gap-2 px-3.5 py-2 font-semibold rounded-t-lg transition-colors ${
            activeTab === 'diagnostics'
              ? 'text-white border-b-2 border-[#7565F5] bg-white/[0.04]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Cpu className="w-3.5 h-3.5 text-cyan-400" />
          <span>Hardware & Snapshots</span>
        </button>
      </div>

      {/* Error Alert Banner */}
      {accessError && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{accessError}</span>
          </div>
          <button
            onClick={() => setAccessError(null)}
            className="p-1 hover:bg-rose-500/20 rounded-lg text-rose-300"
            title="Dismiss error"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* MAIN TAB: GUIDED USER ENTRY MANAGEMENT WORKFLOW                    */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'terminal' && (
        <div className="space-y-6">
          {/* ───────────────────────────────────────────────────────────────── */}
          {/* TOP AUTOMATION WORKFLOW PANEL                                     */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <Card className="p-4 rounded-2xl border-white/[0.08] bg-gradient-to-r from-[#0E1322] via-[#12192B] to-[#0E1322] shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                    automationState === 'PAUSED'
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-lg shadow-amber-500/20'
                      : isAutomationRunning
                      ? 'bg-[#7565F5]/20 text-[#9B8DFC] shadow-lg shadow-[#7565F5]/20 animate-pulse'
                      : automationState === 'ACCESS_ALLOWED'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : automationState === 'ACCESS_DENIED'
                      ? 'bg-rose-500/20 text-rose-400'
                      : automationState === 'MANUAL_REVIEW_REQUIRED'
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-white/[0.06] text-slate-400'
                  }`}
                >
                  {automationState === 'PAUSED' ? (
                    <Pause className="w-5 h-5 text-amber-400" />
                  ) : (
                    <Workflow className="w-5 h-5" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold text-white tracking-wide">
                      AUTOMATED VERIFICATION WORKFLOW
                    </h2>
                    <StatusBadge
                      variant={
                        automationState === 'PAUSED'
                          ? 'warning'
                          : isAutomationRunning
                          ? 'warning'
                          : automationState === 'ACCESS_ALLOWED'
                          ? 'success'
                          : automationState === 'ACCESS_DENIED' || automationState === 'ERROR'
                          ? 'error'
                          : automationState === 'MANUAL_REVIEW_REQUIRED'
                          ? 'warning'
                          : 'neutral'
                      }
                      size="sm"
                      pulse={isAutomationRunning || automationState === 'PAUSED'}
                    >
                      {automationState === 'PAUSED' ? 'PAUSED' : automationState.replace(/_/g, ' ')}
                    </StatusBadge>
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5">{automationMsg}</p>
                </div>
              </div>

              {/* Automation Action Controls: Start / Pause / Resume / Stop */}
              <div className="flex items-center gap-2">
                {isAutomationRunning ? (
                  <>
                    <Button
                      variant="secondary"
                      size="md"
                      onClick={() => pauseAutomation()}
                      leftIcon={<Pause className="w-4 h-4 text-amber-400" />}
                      className="bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border-amber-500/30 font-bold shadow-lg shadow-amber-500/10"
                    >
                      Pause Automation
                    </Button>
                    <Button
                      variant="danger"
                      size="md"
                      onClick={stopAutomation}
                      leftIcon={<Square className="w-4 h-4" />}
                      className="shadow-lg shadow-rose-500/20 font-bold"
                    >
                      Stop Automation
                    </Button>
                  </>
                ) : isAutomationPaused ? (
                  <>
                    <Button
                      variant="primary"
                      size="md"
                      onClick={resumeAutomation}
                      leftIcon={<Play className="w-4 h-4" />}
                      className="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold shadow-lg shadow-emerald-500/20 border-none"
                    >
                      Resume Automation
                    </Button>
                    <Button
                      variant="danger"
                      size="md"
                      onClick={stopAutomation}
                      leftIcon={<Square className="w-4 h-4" />}
                      className="shadow-lg shadow-rose-500/20 font-bold"
                    >
                      Stop Automation
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="primary"
                    size="md"
                    onClick={startAutomation}
                    leftIcon={<Play className="w-4 h-4" />}
                    className="bg-gradient-to-r from-[#7565F5] to-[#5846E2] text-white font-bold shadow-lg shadow-[#7565F5]/30 hover:shadow-[#7565F5]/50 border-none"
                  >
                    Start Automation
                  </Button>
                )}
              </div>
            </div>

            {/* Stepper Progress Indicator */}
            <div className="pt-3">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                {/* Step 1: Camera */}
                <div
                  className={`p-2.5 rounded-xl border flex items-center gap-2 transition-all ${
                    cameraStatus === 'live'
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                      : automationState === 'INITIALIZING_CAMERA'
                      ? 'bg-amber-500/10 border-amber-500/25 text-amber-300 animate-pulse'
                      : 'bg-[#0B101D] border-white/[0.04] text-slate-400'
                  }`}
                >
                  <Camera className="w-3.5 h-3.5 shrink-0" />
                  <div className="truncate">
                    <div className="text-[10px] font-mono text-slate-400">STAGE 1</div>
                    <div className="font-semibold text-slate-200 truncate">Camera Ready</div>
                  </div>
                </div>

                {/* Step 2: Face */}
                <div
                  className={`p-2.5 rounded-xl border flex items-center gap-2 transition-all ${
                    automationState === 'PAUSED' && resumeCheckpoint === 'FACE_VERIFICATION'
                      ? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
                      : automationState === 'FACE_VERIFIED' ||
                        automationState === 'PLATE_VERIFICATION' ||
                        automationState === 'PLATE_VERIFIED' ||
                        automationState === 'EVALUATING_ACCESS' ||
                        automationState === 'ACCESS_ALLOWED'
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                      : automationState === 'FACE_VERIFICATION'
                      ? 'bg-cyan-500/10 border-cyan-500/25 text-cyan-300 animate-pulse'
                      : 'bg-[#0B101D] border-white/[0.04] text-slate-400'
                  }`}
                >
                  <ScanFace className="w-3.5 h-3.5 shrink-0" />
                  <div className="truncate">
                    <div className="text-[10px] font-mono text-slate-400">STAGE 2</div>
                    <div className="font-semibold text-slate-200 truncate">
                      {automationState === 'PAUSED' && resumeCheckpoint === 'FACE_VERIFICATION'
                        ? 'Face (PAUSED)'
                        : 'Face Verification'}
                    </div>
                  </div>
                </div>

                {/* Step 3: Plate */}
                <div
                  className={`p-2.5 rounded-xl border flex items-center gap-2 transition-all ${
                    automationState === 'PAUSED' && resumeCheckpoint === 'PLATE_VERIFICATION'
                      ? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
                      : automationState === 'PLATE_VERIFIED' ||
                        automationState === 'EVALUATING_ACCESS' ||
                        automationState === 'ACCESS_ALLOWED'
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                      : automationState === 'PLATE_VERIFICATION'
                      ? 'bg-amber-500/10 border-amber-500/25 text-amber-300 animate-pulse'
                      : 'bg-[#0B101D] border-white/[0.04] text-slate-400'
                  }`}
                >
                  <Car className="w-3.5 h-3.5 shrink-0" />
                  <div className="truncate">
                    <div className="text-[10px] font-mono text-slate-400">STAGE 3</div>
                    <div className="font-semibold text-slate-200 truncate">
                      {automationState === 'PAUSED' && resumeCheckpoint === 'PLATE_VERIFICATION'
                        ? 'Plate OCR (PAUSED)'
                        : 'Plate OCR'}
                    </div>
                  </div>
                </div>

                {/* Step 4: Decision Evaluation */}
                <div
                  className={`p-2.5 rounded-xl border flex items-center gap-2 transition-all ${
                    automationState === 'PAUSED' && (resumeCheckpoint === 'PLATE_VERIFIED' || resumeCheckpoint === 'EVALUATING_ACCESS')
                      ? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
                      : automationState === 'ACCESS_ALLOWED' ||
                        automationState === 'ACCESS_DENIED' ||
                        automationState === 'MANUAL_REVIEW_REQUIRED'
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                      : automationState === 'EVALUATING_ACCESS'
                      ? 'bg-[#7565F5]/20 border-[#7565F5]/40 text-[#9B8DFC] animate-pulse'
                      : 'bg-[#0B101D] border-white/[0.04] text-slate-400'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                  <div className="truncate">
                    <div className="text-[10px] font-mono text-slate-400">STAGE 4</div>
                    <div className="font-semibold text-slate-200 truncate">
                      {automationState === 'PAUSED' && (resumeCheckpoint === 'PLATE_VERIFIED' || resumeCheckpoint === 'EVALUATING_ACCESS')
                        ? 'Policy (PAUSED)'
                        : 'Access Policy'}
                    </div>
                  </div>
                </div>

                {/* Step 5: Gate Result */}
                <div
                  className={`p-2.5 rounded-xl border flex items-center gap-2 transition-all ${
                    automationState === 'ACCESS_ALLOWED'
                      ? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300'
                      : automationState === 'ACCESS_DENIED'
                      ? 'bg-rose-500/15 border-rose-500/35 text-rose-300'
                      : automationState === 'MANUAL_REVIEW_REQUIRED'
                      ? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
                      : 'bg-[#0B101D] border-white/[0.04] text-slate-400'
                  }`}
                >
                  {automationState === 'ACCESS_ALLOWED' ? (
                    <Unlock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : automationState === 'MANUAL_REVIEW_REQUIRED' ? (
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  ) : automationState === 'ACCESS_DENIED' ? (
                    <ShieldX className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                  ) : (
                    <Lock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                  )}
                  <div className="truncate">
                    <div className="text-[10px] font-mono text-slate-400">RESULT</div>
                    <div className="font-semibold text-slate-200 truncate">
                      {automationState === 'ACCESS_ALLOWED'
                        ? 'Gate Opened'
                        : automationState === 'ACCESS_DENIED'
                        ? 'Gate Denied'
                        : automationState === 'MANUAL_REVIEW_REQUIRED'
                        ? 'Review Needed'
                        : 'Standby'}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Prominent Paused Status Banner */}
            {automationState === 'PAUSED' && (
              <div className="mt-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex flex-wrap items-center justify-between gap-3 text-xs text-amber-300 animate-in fade-in">
                <div className="flex items-center gap-2.5">
                  <Pause className="w-4 h-4 text-amber-400 shrink-0 animate-pulse" />
                  <div>
                    <span className="font-bold text-amber-200 uppercase tracking-wider">Automation Paused:</span>{' '}
                    <span>Automation is paused. Verification will not proceed until you resume. Safe checkpoint:{' '}
                      <span className="font-mono font-bold text-amber-100 bg-amber-500/20 px-1.5 py-0.5 rounded">
                        {resumeCheckpoint?.replace(/_/g, ' ') || 'CURRENT STAGE'}
                      </span>
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-amber-400/80 font-mono">Lane: {direction}</span>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={resumeAutomation}
                    leftIcon={<Play className="w-3.5 h-3.5" />}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold border-none shadow-md shadow-emerald-600/30"
                  >
                    Resume Now
                  </Button>
                </div>
              </div>
            )}
          </Card>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* STAGE B: FACE RECOGNITION STAGE                                   */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <Card className="border-white/[0.08] bg-[#0E1322] overflow-hidden">
            <CardHeader className="p-4 border-b border-white/[0.06] flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center">
                  <ScanFace className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <span>Stage 1: Facial Recognition & Verification</span>
                    <span className="text-[10px] font-mono font-normal text-slate-400">InsightFace ArcFace</span>
                  </CardTitle>
                  <p className="text-xs text-slate-400">Biometric identity verification against enrolled campus records.</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <StatusBadge
                  variant={
                    faceStageState === 'VERIFIED'
                      ? 'success'
                      : faceStageState === 'MAX_ATTEMPTS_REACHED' || faceStageState === 'FAILED'
                      ? 'error'
                      : faceStageState === 'SCANNING' || faceStageState === 'VERIFYING'
                      ? 'warning'
                      : 'neutral'
                  }
                  size="sm"
                  pulse={faceStageState === 'SCANNING' || faceStageState === 'VERIFYING'}
                >
                  {faceStageState.replace('_', ' ')}
                </StatusBadge>

                {faceStageState === 'SCANNING' || faceStageState === 'VERIFYING' ? (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={stopFaceVerification}
                    leftIcon={<Square className="w-3 h-3" />}
                    disabled={isAutomationActive}
                    title={isAutomationRunning ? 'Stop Automation from the top control panel' : isAutomationPaused ? 'Automation is paused. Resume or stop automation to proceed manually.' : undefined}
                  >
                    Stop Face Verification
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={startFaceVerification}
                    disabled={faceStageState === 'VERIFIED' || isAutomationActive}
                    leftIcon={<Play className="w-3 h-3" />}
                    className="bg-cyan-600 hover:bg-cyan-500 text-white border-none shadow-md shadow-cyan-600/20 disabled:opacity-50"
                    title={isAutomationActive ? 'Automation is currently active or paused.' : undefined}
                  >
                    {faceStageState === 'MAX_ATTEMPTS_REACHED' ? 'Retry Face Verification' : 'Start Face Verification'}
                  </Button>
                )}
              </div>
            </CardHeader>

            <CardContent className="p-4">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
                {/* Left: Camera Preview & Bounding Box Overlay */}
                <div className="lg:col-span-7 flex flex-col">
                  <div
                    ref={faceContainerRef}
                    className="relative w-full aspect-video min-h-[260px] max-h-[380px] bg-slate-950 rounded-xl overflow-hidden border border-white/[0.08] flex items-center justify-center"
                  >
                    <video
                      ref={faceVideoRef}
                      playsInline
                      muted
                      autoPlay
                      className={`w-full h-full object-contain ${!isLive ? 'hidden' : ''}`}
                    />
                    <canvas
                      ref={faceOverlayCanvasRef}
                      className={`absolute inset-0 w-full h-full pointer-events-none ${!isLive ? 'hidden' : ''}`}
                    />

                    {!isLive && (
                      <div className="p-6 text-center space-y-3">
                        <ScanFace className="w-10 h-10 text-cyan-400 mx-auto opacity-50" />
                        <p className="text-xs text-slate-400">{cameraError || 'Camera feed offline'}</p>
                        <Button variant="secondary" size="sm" onClick={startCamera}>
                          Start Camera
                        </Button>
                      </div>
                    )}

                    <div className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md border border-white/[0.08] text-[10px] font-mono text-cyan-300 flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-cyan-400 animate-pulse' : 'bg-slate-500'}`} />
                      <span>FACE OPTICAL SENSOR</span>
                    </div>
                  </div>

                  <div className="mt-2 text-[11px] text-slate-400 flex items-center justify-between px-1">
                    <span>Threshold: Cosine Sim &ge; 0.45</span>
                    <span>Single-flight frame evaluation</span>
                  </div>
                </div>

                {/* Right: Face Verification Information & Guidance */}
                <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
                  <div className="space-y-3">
                    {/* Face Match Details */}
                    <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-2">
                      <div className="text-[11px] font-mono text-slate-400">FACE STATUS & IDENTITY</div>
                      <div className="text-sm font-semibold text-slate-100 flex items-center justify-between">
                        <span>
                          {verifiedFace?.person?.name
                            ? verifiedFace.person.name
                            : currentFaces.length > 0 && currentFaces[0].person?.name
                            ? currentFaces[0].person.name
                            : faceStageState === 'VERIFIED'
                            ? 'Identity Confirmed'
                            : faceStageState === 'SCANNING'
                            ? 'Scanning for face...'
                            : 'No face verified'}
                        </span>
                        <StatusBadge
                          variant={
                            faceStageState === 'VERIFIED'
                              ? 'success'
                              : faceStageState === 'FAILED' || faceStageState === 'MAX_ATTEMPTS_REACHED'
                              ? 'error'
                              : 'neutral'
                          }
                          size="sm"
                        >
                          {faceStageState === 'VERIFIED'
                            ? 'VERIFIED'
                            : currentFaces.length > 0
                            ? currentFaces[0].status.toUpperCase()
                            : 'IDLE'}
                        </StatusBadge>
                      </div>

                      {verifiedFace?.person?.person_type && (
                        <p className="text-xs text-slate-400">
                          Role: <span className="text-slate-200 capitalize">{verifiedFace.person.person_type}</span>
                        </p>
                      )}
                    </div>

                    {/* Similarity Score */}
                    <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-1.5">
                      <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
                        <span>SIMILARITY SCORE (COSINE)</span>
                        <span className="text-cyan-400 font-semibold">
                          {verifiedFace?.score !== undefined && verifiedFace?.score !== null
                            ? `${verifiedFace.score.toFixed(3)}`
                            : currentFaces.length > 0 && currentFaces[0].score !== undefined && currentFaces[0].score !== null
                            ? `${currentFaces[0].score.toFixed(3)}`
                            : 'N/A'}
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full transition-all duration-300 ${
                            (verifiedFace?.score ?? currentFaces[0]?.score ?? 0) >= 0.45
                              ? 'bg-emerald-400'
                              : 'bg-amber-400'
                          }`}
                          style={{
                            width: `${Math.min(100, Math.max(0, ((verifiedFace?.score ?? currentFaces[0]?.score ?? 0) / 0.8) * 100))}%`,
                          }}
                        />
                      </div>
                      <p className="text-[10px] text-slate-500">
                        Clearance requirement: Cosine similarity score &ge; 0.45 (Not a probability).
                      </p>
                    </div>

                    {/* Three-Attempt Limit Counter */}
                    <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono text-slate-400">FAILED ATTEMPTS:</span>
                        <span
                          className={`font-mono font-bold ${
                            failedFaceAttempts >= 3
                              ? 'text-rose-400'
                              : failedFaceAttempts > 0
                              ? 'text-amber-400'
                              : 'text-slate-300'
                          }`}
                        >
                          {failedFaceAttempts} / 3
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        {[1, 2, 3].map((attemptNum) => (
                          <div
                            key={attemptNum}
                            className={`h-2 rounded-full transition-all ${
                              failedFaceAttempts >= attemptNum
                                ? 'bg-rose-500 shadow-sm shadow-rose-500/50'
                                : 'bg-slate-800'
                            }`}
                          />
                        ))}
                      </div>

                      {failedFaceAttempts >= 3 && (
                        <p className="text-[11px] text-rose-400 font-medium">
                          Terminal limit reached. Continuous frame capture locked for this attempt.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Contextual Guidance Box */}
                  <div className="p-3.5 rounded-xl bg-[#13192B] border border-cyan-500/20 text-xs text-cyan-200 flex items-start gap-2.5">
                    <HelpCircle className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-white">Guidance & Instructions:</div>
                      <p className="text-[11px] text-slate-300 mt-0.5 leading-relaxed">{faceGuidance}</p>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* STAGE C: NUMBER PLATE RECOGNITION STAGE                           */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <Card className="border-white/[0.08] bg-[#0E1322] overflow-hidden">
            <CardHeader className="p-4 border-b border-white/[0.06] flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
                  <Car className="w-4 h-4" />
                </div>
                <div>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <span>Stage 2: Number Plate Recognition (FastALPR)</span>
                    <span className="text-[10px] font-mono font-normal text-slate-400">Mobile-ViT OCR</span>
                  </CardTitle>
                  <p className="text-xs text-slate-400">Automated vehicle plate OCR and campus registration validation.</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <StatusBadge
                  variant={
                    plateStageState === 'REGISTERED'
                      ? 'success'
                      : plateStageState === 'FLAGGED'
                      ? 'error'
                      : plateStageState === 'UNREGISTERED'
                      ? 'warning'
                      : plateStageState === 'SCANNING'
                      ? 'warning'
                      : 'neutral'
                  }
                  size="sm"
                  pulse={plateStageState === 'SCANNING'}
                >
                  {plateStageState.replace('_', ' ')}
                </StatusBadge>

                {plateStageState === 'SCANNING' ? (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={stopPlateVerification}
                    leftIcon={<Square className="w-3 h-3" />}
                    disabled={isAutomationActive}
                    title={isAutomationRunning ? 'Stop Automation from the top control panel' : isAutomationPaused ? 'Automation is paused. Resume or stop automation to proceed manually.' : undefined}
                  >
                    Stop Plate Verification
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={startPlateVerification}
                    leftIcon={<Play className="w-3 h-3" />}
                    disabled={isAutomationActive}
                    className="bg-amber-600 hover:bg-amber-500 text-white border-none shadow-md shadow-amber-600/20 disabled:opacity-50"
                    title={isAutomationActive ? 'Automation is currently active or paused.' : undefined}
                  >
                    Start Plate Verification
                  </Button>
                )}
              </div>
            </CardHeader>

            <CardContent className="p-4">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
                {/* Left: Reused Camera Preview & Plate Overlay */}
                <div className="lg:col-span-7 flex flex-col">
                  <div
                    ref={plateContainerRef}
                    className="relative w-full aspect-video min-h-[260px] max-h-[380px] bg-slate-950 rounded-xl overflow-hidden border border-white/[0.08] flex items-center justify-center"
                  >
                    <video
                      ref={plateVideoRef}
                      playsInline
                      muted
                      autoPlay
                      className={`w-full h-full object-contain ${!isLive ? 'hidden' : ''}`}
                    />
                    <canvas
                      ref={plateOverlayCanvasRef}
                      className={`absolute inset-0 w-full h-full pointer-events-none ${!isLive ? 'hidden' : ''}`}
                    />

                    {!isLive && (
                      <div className="p-6 text-center space-y-3">
                        <Car className="w-10 h-10 text-amber-400 mx-auto opacity-50" />
                        <p className="text-xs text-slate-400">Camera feed offline</p>
                      </div>
                    )}

                    <div className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md border border-white/[0.08] text-[10px] font-mono text-amber-300 flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-amber-400 animate-pulse' : 'bg-slate-500'}`} />
                      <span>ALPR LANE SENSOR</span>
                    </div>
                  </div>

                  <div className="mt-2 text-[11px] text-slate-400 flex items-center justify-between px-1">
                    <span>Reused hardware stream • Zero duplicate inference</span>
                    <span>State plate normalization active</span>
                  </div>
                </div>

                {/* Right: Plate Verification Information & Guidance */}
                <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
                  <div className="space-y-3">
                    {/* Plate Detection Details */}
                    <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-2">
                      <div className="text-[11px] font-mono text-slate-400">RECOGNIZED REGISTRATION NUMBER</div>
                      <div className="text-lg font-mono font-bold text-white tracking-widest flex items-center justify-between">
                        <span>
                          {verifiedPlate?.normalized_plate || verifiedPlate?.label || (currentPlates[0]?.normalized_plate ?? '— — — —')}
                        </span>
                        <StatusBadge
                          variant={
                            plateStageState === 'REGISTERED'
                              ? 'success'
                              : plateStageState === 'FLAGGED'
                              ? 'error'
                              : plateStageState === 'UNREGISTERED'
                              ? 'warning'
                              : 'neutral'
                          }
                          size="sm"
                        >
                          {verifiedPlate?.status ? verifiedPlate.status.toUpperCase() : 'PENDING'}
                        </StatusBadge>
                      </div>
                      {verifiedPlate?.ocr_confidence !== undefined && verifiedPlate?.ocr_confidence !== null && (
                        <p className="text-[11px] text-slate-400">
                          OCR Confidence: <span className="text-amber-400 font-mono">{(verifiedPlate.ocr_confidence * 100).toFixed(1)}%</span>
                        </p>
                      )}
                    </div>

                    {/* Registered Vehicle Info */}
                    <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-1.5 text-xs">
                      <div className="text-[11px] font-mono text-slate-400">CAMPUS REGISTRATION RECORD</div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Registered Owner:</span>
                        <span className="text-slate-200 font-medium">
                          {verifiedPlate?.vehicle?.owner_name || 'No Owner Record'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Vehicle Status:</span>
                        <span className="text-slate-200 font-medium capitalize">
                          {verifiedPlate?.vehicle?.status || (plateStageState === 'UNREGISTERED' ? 'Unregistered' : 'Pending Check')}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Vehicle Model:</span>
                        <span className="text-slate-200 font-medium">
                          {verifiedPlate?.vehicle
                            ? `${verifiedPlate.vehicle.make || ''} ${verifiedPlate.vehicle.model || ''}`.trim() || '—'
                            : '—'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Contextual Plate Guidance */}
                  <div className="p-3.5 rounded-xl bg-[#13192B] border border-amber-500/20 text-xs text-amber-200 flex items-start gap-2.5">
                    <HelpCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-white">Plate Stage Instructions:</div>
                      <p className="text-[11px] text-slate-300 mt-0.5 leading-relaxed">{plateGuidance}</p>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* SECTION 3: PERSISTENT IDENTITY AND VEHICLE MATCH SUMMARY           */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Card 1: IDENTITY MATCH */}
            <Card className="p-4 border-white/[0.08] bg-[#0E1322] space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
                  <ScanFace className="w-3.5 h-3.5 text-cyan-400" />
                  <span>IDENTITY MATCH</span>
                </div>
                <StatusBadge variant={identityStatus.variant} size="sm">
                  {identityStatus.text.toUpperCase()}
                </StatusBadge>
              </div>

              <div className="space-y-1">
                <div className="text-sm font-bold text-slate-100 truncate">
                  {verifiedFace?.person?.name || 'Pending Identification'}
                </div>
                <div className="text-xs text-slate-400 flex items-center justify-between">
                  <span>Role: {verifiedFace?.person?.person_type || '—'}</span>
                  <span>
                    Sim: {verifiedFace?.score !== undefined && verifiedFace?.score !== null ? verifiedFace.score.toFixed(2) : '—'}
                  </span>
                </div>
              </div>
            </Card>

            {/* Card 2: VEHICLE MATCH */}
            <Card className="p-4 border-white/[0.08] bg-[#0E1322] space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
                  <Car className="w-3.5 h-3.5 text-amber-400" />
                  <span>VEHICLE MATCH</span>
                </div>
                <StatusBadge variant={vehicleStatus.variant} size="sm">
                  {vehicleStatus.text.toUpperCase()}
                </StatusBadge>
              </div>

              <div className="space-y-1">
                <div className="text-sm font-bold text-slate-100 font-mono truncate">
                  {verifiedPlate?.normalized_plate || 'Pending Vehicle OCR'}
                </div>
                <div className="text-xs text-slate-400 flex items-center justify-between">
                  <span>Owner: {verifiedPlate?.vehicle?.owner_name || '—'}</span>
                  <span className="capitalize">{verifiedPlate?.vehicle?.status || '—'}</span>
                </div>
              </div>
            </Card>

            {/* Card 3: ACCESS DECISION */}
            <Card className="p-4 border-white/[0.08] bg-[#0E1322] space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5 text-indigo-400" />
                  <span>ACCESS DECISION</span>
                </div>
                <StatusBadge variant={decisionStatus.variant} size="sm">
                  {decisionStatus.text}
                </StatusBadge>
              </div>

              <div className="space-y-1">
                <div className="text-sm font-bold text-slate-100">
                  {lastDecision ? `GATE ${lastDecision.gate_result}` : 'Awaiting Evaluation'}
                </div>
                <p className="text-xs text-slate-400 truncate">
                  {lastDecision?.reason_text || 'Deterministic Phase 3 policy verification'}
                </p>
              </div>
            </Card>
          </div>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* SECTION 4: EVALUATE GATE ACCESS & SIMULATED BARRIER CONTROL        */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/[0.06]">
              <div>
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                  <span>Phase 3 Access Decision Engine</span>
                </h3>
                <p className="text-xs text-slate-400">
                  Evaluates biometric verification, vehicle ownership map (vehicles.owner_person_id), active schedule, and watchlist.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="primary"
                  size="md"
                  onClick={evaluateGateAccess}
                  isLoading={isSubmittingAttempt}
                  disabled={isAutomationActive}
                  leftIcon={<ShieldCheck className="w-4 h-4" />}
                  className="bg-gradient-to-r from-[#7565F5] to-[#5a48e6] text-white font-bold shadow-lg shadow-[#7565F5]/25 disabled:opacity-50"
                  title={isAutomationRunning ? 'Automation handles gate evaluation automatically' : isAutomationPaused ? 'Automation is paused. Resume or stop automation from the top panel.' : undefined}
                >
                  Evaluate Gate Access
                </Button>

                <Button
                  variant="secondary"
                  size="md"
                  onClick={handleResetGate}
                  title="Reset barrier to closed state"
                  leftIcon={<Lock className="w-3.5 h-3.5" />}
                >
                  Reset Barrier
                </Button>
              </div>
            </div>

            {/* Simulated Barrier Status Bar */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
              <div
                className={`p-4 rounded-xl border flex items-center gap-3.5 transition-all ${
                  (gateStatus?.state === 'OPEN' || gateStatus?.state === 'MANUAL_LATCHED_OPEN')
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                    : gateStatus?.state === 'MANUAL_REVIEW'
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                    : 'bg-slate-800/40 border-white/[0.08] text-slate-300'
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                    (gateStatus?.state === 'OPEN' || gateStatus?.state === 'MANUAL_LATCHED_OPEN')
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : gateStatus?.state === 'MANUAL_REVIEW'
                      ? 'bg-amber-500/20 text-amber-400 animate-pulse'
                      : 'bg-white/[0.06] text-slate-400'
                  }`}
                >
                  {gateStatus?.state === 'OPEN' || gateStatus?.state === 'MANUAL_LATCHED_OPEN' ? (
                    <Unlock className="w-5 h-5" />
                  ) : gateStatus?.state === 'MANUAL_REVIEW' ? (
                    <ShieldAlert className="w-5 h-5" />
                  ) : (
                    <Lock className="w-5 h-5" />
                  )}
                </div>
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Software Gate State</div>
                  <div className="text-base font-bold flex items-center gap-2">
                    <span>{gateStatus?.state || 'CLOSED'}</span>
                    {gateStatus?.state === 'OPEN' && (
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full font-mono">
                        Auto-close 15s
                      </span>
                    )}
                    {gateStatus?.state === 'MANUAL_LATCHED_OPEN' && (
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full font-mono">
                        Manual latch
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-500">Controller movement is not sensor-verified.</div>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-1">
                <div className="text-[11px] font-mono text-slate-400">LAST ACTION & DIRECTION</div>
                <div className="text-xs text-slate-200 font-medium">
                  Decision: <span className="font-semibold">{gateStatus?.last_decision || 'NONE'}</span> • Direction: {gateStatus?.last_direction || direction}
                </div>
                <div className="text-[10px] text-slate-500 truncate">
                  Transition: {gateStatus?.last_transition_at ? new Date(gateStatus.last_transition_at).toLocaleTimeString() : 'Ready'}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-1">
                <div className="text-[11px] font-mono text-slate-400">SIMULATED HARDWARE</div>
                <div className="text-xs text-slate-300 font-mono truncate">
                  {gateStatus?.simulation_note || 'Software simulation only; physical position is not sensor-verified.'}
                </div>
              </div>
            </div>

            {/* Decision Outcome Card with Matrix */}
            {lastDecision && (
              <div
                className={`p-4 rounded-xl border space-y-3 ${
                  lastDecision.decision === 'ALLOW'
                    ? 'bg-emerald-950/20 border-emerald-500/30'
                    : lastDecision.decision === 'DENY'
                    ? 'bg-rose-950/20 border-rose-500/30'
                    : 'bg-amber-950/20 border-amber-500/30'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                        lastDecision.decision === 'ALLOW'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : lastDecision.decision === 'DENY'
                          ? 'bg-rose-500/20 text-rose-400'
                          : 'bg-amber-500/20 text-amber-400'
                      }`}
                    >
                      {lastDecision.decision === 'ALLOW' ? (
                        <ShieldCheck className="w-5 h-5" />
                      ) : lastDecision.decision === 'DENY' ? (
                        <ShieldX className="w-5 h-5" />
                      ) : (
                        <ShieldAlert className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-100">
                          DECISION: {lastDecision.decision}
                        </span>
                        <StatusBadge
                          variant={
                            lastDecision.decision === 'ALLOW'
                              ? 'success'
                              : lastDecision.decision === 'DENY'
                              ? 'error'
                              : 'warning'
                          }
                          size="sm"
                        >
                          GATE {lastDecision.gate_result}
                        </StatusBadge>
                      </div>
                      <p className="text-xs text-slate-300 mt-0.5">{lastDecision.reason_text}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {(lastDecision.reason_codes || []).map((code) => (
                      <span
                        key={code}
                        className="px-2 py-0.5 rounded text-[10px] font-mono bg-white/[0.06] text-slate-300 border border-white/[0.08]"
                      >
                        {code}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 pt-2 border-t border-white/[0.06] text-xs">
                  <div className="p-2.5 rounded-lg bg-[#0B101D]/70 border border-white/[0.04]">
                    <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                      <ScanFace className="w-3 h-3 text-cyan-400" /> Identity
                    </div>
                    <div className="mt-1 font-semibold text-slate-200 truncate">
                      {lastDecision.person_status ? `Status: ${lastDecision.person_status}` : 'No Face'}
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#0B101D]/70 border border-white/[0.04]">
                    <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                      <Car className="w-3 h-3 text-amber-400" /> Plate
                    </div>
                    <div className="mt-1 font-semibold text-slate-200 truncate font-mono">
                      {lastDecision.detected_plate || 'No Plate'}
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#0B101D]/70 border border-white/[0.04]">
                    <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                      <Shield className="w-3 h-3 text-indigo-400" /> Ownership
                    </div>
                    <div className="mt-1 font-semibold text-slate-200">
                      {lastDecision.ownership_ok === true ? (
                        <span className="text-emerald-400">Verified Owner ✓</span>
                      ) : lastDecision.ownership_ok === false ? (
                        <span className="text-amber-400">Owner Mismatch ✗</span>
                      ) : (
                        'N/A'
                      )}
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#0B101D]/70 border border-white/[0.04]">
                    <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-emerald-400" /> Schedule & Watchlist
                    </div>
                    <div className="mt-1 font-semibold text-slate-200">
                      {lastDecision.watchlist_hit ? (
                        <span className="text-rose-400">Watchlist Blocked!</span>
                      ) : lastDecision.schedule_ok === false ? (
                        <span className="text-amber-400">Outside Operating Hours</span>
                      ) : (
                        <span className="text-emerald-400">Schedule Permitted ✓</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Card>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* SECTION 5: MANUAL SECURITY VERIFICATION & VISITOR MANAGEMENT      */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Manual Security Verification Card */}
            <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
                    <ListFilter className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                      <span>Manual Security Verification</span>
                      {pendingReviews.length > 0 && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/20 text-amber-300 font-mono font-bold">
                          {pendingReviews.length} PENDING
                        </span>
                      )}
                    </h4>
                    <p className="text-xs text-slate-400">Officer intervention queue for ambiguous cases or owner mismatches.</p>
                  </div>
                </div>
              </div>

              {pendingReviews.length === 0 ? (
                <div className="p-4 rounded-xl bg-[#0B101D] border border-white/[0.04] text-center text-xs text-slate-400 space-y-1">
                  <CheckCircle className="w-6 h-6 text-emerald-400 mx-auto opacity-70" />
                  <p className="font-medium text-slate-200">All Manual Reviews Cleared</p>
                  <p className="text-[11px] text-slate-500">No attempts currently awaiting officer intervention.</p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[300px] overflow-y-auto">
                  {pendingReviews.map((item) => (
                    <div
                      key={item.id}
                      className="p-3 rounded-xl bg-[#0B101D] border border-white/[0.06] space-y-2.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <StatusBadge variant="warning" size="sm">
                            {item.direction}
                          </StatusBadge>
                          <span className="font-mono text-slate-200">{item.detected_plate || 'No Plate'}</span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500">
                          {new Date(item.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300">{item.reason_text}</p>

                      {reviewingId === item.id ? (
                        <div className="space-y-2 pt-2 border-t border-white/[0.06]">
                          <input
                            type="text"
                            placeholder="Clearance note (required to deny)..."
                            value={reviewNote}
                            onChange={(e) => setReviewNote(e.target.value)}
                            className="w-full bg-[#13192B] border border-white/[0.1] rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5]"
                          />
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setReviewingId(null);
                                setReviewNote('');
                              }}
                            >
                              Cancel
                            </Button>
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => resolveReview(item.id, 'denied')}
                              isLoading={isResolvingReview}
                              leftIcon={<Lock className="w-3 h-3" />}
                            >
                              Deny Entry
                            </Button>
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => resolveReview(item.id, 'approved')}
                              isLoading={isResolvingReview}
                              leftIcon={<Unlock className="w-3 h-3" />}
                              className="bg-emerald-600 hover:bg-emerald-500 border-none"
                            >
                              Authorize & Open
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex justify-end pt-1">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              setReviewingId(item.id);
                              setReviewNote('');
                            }}
                            leftIcon={<Eye className="w-3 h-3" />}
                          >
                            Review & Resolve
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* Visitor Management Card */}
            <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-4 flex flex-col justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
                    <UserPlus className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-100">Visitor Management</h4>
                    <p className="text-xs text-slate-400">Pre-registered guests, visitor passes, and temporary access clearance.</p>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.04] space-y-1.5 text-xs text-slate-300">
                  <p className="text-slate-400">
                    Visitors without biometric enrollment or registered plates require manual badge issuance or pre-registration verification.
                  </p>
                  <div className="flex items-center gap-2 pt-1 text-[11px] text-indigo-300 font-mono">
                    <UserCheck className="w-3.5 h-3.5" />
                    <span>Temporary 1-day pass authorization ready</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setIsVisitorModalOpen(true)}
                  leftIcon={<UserPlus className="w-3.5 h-3.5" />}
                  className="bg-[#7565F5] hover:bg-[#6353E8] text-white border-none"
                >
                  Quick Pass
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate('/security/visitors')}
                  leftIcon={<QrCode className="w-3.5 h-3.5 text-sky-400" />}
                >
                  Visitor Terminal
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate('/admin/people')}
                  leftIcon={<Eye className="w-3.5 h-3.5" />}
                >
                  Lookup Directory
                </Button>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* VISITOR MANAGEMENT MODAL                                            */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {isVisitorModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <Card className="max-w-md w-full p-5 border-white/[0.1] bg-[#0E1322] space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
              <div className="flex items-center gap-2 text-indigo-400">
                <UserPlus className="w-5 h-5" />
                <h3 className="text-sm font-bold text-slate-100">Issue Temporary Visitor Pass</h3>
              </div>
              <button
                onClick={() => setIsVisitorModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {visitorSuccessMsg ? (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <span>{visitorSuccessMsg}</span>
              </div>
            ) : (
              <form onSubmit={handleIssueVisitorPass} className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1">Visitor Full Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Jane Doe"
                    value={visitorName}
                    onChange={(e) => setVisitorName(e.target.value)}
                    className="w-full bg-[#13192B] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5]"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Vehicle License Plate (if vehicle entry)</label>
                  <input
                    type="text"
                    placeholder="e.g. MH12AB1234"
                    value={visitorPlate}
                    onChange={(e) => setVisitorPlate(e.target.value)}
                    className="w-full bg-[#13192B] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5] font-mono uppercase"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Campus Host / Sponsor</label>
                  <input
                    type="text"
                    placeholder="e.g. Dr. Rajesh Kumar (Faculty)"
                    value={visitorHost}
                    onChange={(e) => setVisitorHost(e.target.value)}
                    className="w-full bg-[#13192B] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5]"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Purpose of Visit</label>
                  <select
                    value={visitorPurpose}
                    onChange={(e) => setVisitorPurpose(e.target.value)}
                    className="w-full bg-[#13192B] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-[#7565F5]"
                  >
                    <option value="Campus Meeting">Official Campus Meeting</option>
                    <option value="Delivery / Vendor">Delivery or Vendor</option>
                    <option value="Guest Lecture">Guest Speaker / Seminar</option>
                    <option value="Maintenance">Maintenance Contractor</option>
                  </select>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/[0.08]">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsVisitorModalOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    className="bg-[#7565F5] hover:bg-[#6353E8] text-white"
                    isLoading={isIssuingVisitor}
                    disabled={isIssuingVisitor}
                  >
                    Authorize & Issue Pass
                  </Button>
                </div>
              </form>
            )}
          </Card>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* SECONDARY TAB: ACCESS AUDIT TRAIL                                   */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'audit' && (
        <Card className="border-white/[0.08] bg-[#0E1322] space-y-4 p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <ClipboardList className="w-5 h-5 text-indigo-400" />
              <div>
                <h3 className="text-sm font-bold text-slate-100">Gate Access Audit Trail</h3>
                <p className="text-xs text-slate-400">Chronological history of evaluated access attempts and overrides.</p>
              </div>
            </div>
            <span className="text-xs font-mono bg-white/[0.06] text-slate-300 px-2.5 py-1 rounded-lg">
              {accessHistory.length} total records
            </span>
          </div>

          <div className="space-y-2.5 max-h-[550px] overflow-y-auto">
            {accessHistory.length === 0 ? (
              <div className="text-center py-12 text-slate-500 space-y-2">
                <Clock className="w-8 h-8 mx-auto opacity-40" />
                <p className="text-xs">No access attempts logged yet.</p>
              </div>
            ) : (
              accessHistory.map((item) => (
                <div
                  key={item.id}
                  className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] hover:border-white/[0.12] transition-colors flex flex-wrap items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                        item.decision === 'ALLOW'
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : item.decision === 'DENY'
                          ? 'bg-rose-500/10 text-rose-400'
                          : 'bg-amber-500/10 text-amber-400'
                      }`}
                    >
                      {item.decision === 'ALLOW' ? (
                        <ShieldCheck className="w-4 h-4" />
                      ) : item.decision === 'DENY' ? (
                        <ShieldX className="w-4 h-4" />
                      ) : (
                        <ShieldAlert className="w-4 h-4" />
                      )}
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-slate-200">
                          {item.detected_plate || 'NO PLATE'}
                        </span>
                        <StatusBadge
                          variant={
                            item.decision === 'ALLOW'
                              ? 'success'
                              : item.decision === 'DENY'
                              ? 'error'
                              : 'warning'
                          }
                          size="sm"
                        >
                          {item.decision}
                        </StatusBadge>
                        <span className="text-[10px] font-mono text-slate-400 bg-white/[0.04] px-1.5 py-0.5 rounded">
                          {item.direction}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5 truncate">{item.reason_text}</p>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-[10px] font-mono text-slate-500">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </div>
                    {item.review_resolved && (
                      <span className="text-[10px] text-emerald-400 font-medium">
                        Reviewed ({item.review_resolution})
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* SECONDARY TAB: ACTIVE WATCHLIST                                     */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'watchlist' && (
        <Card className="border-white/[0.08] bg-[#0E1322] space-y-4 p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <List className="w-5 h-5 text-rose-400" />
              <div>
                <h3 className="text-sm font-bold text-slate-100">Security Watchlist Monitor</h3>
                <p className="text-xs text-slate-400">High-precedence blocking list enforced by Phase 3 decision engine.</p>
              </div>
            </div>
            <span className="text-xs font-mono bg-white/[0.06] text-rose-300 px-2.5 py-1 rounded-lg">
              {watchlist.length} active entries
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[550px] overflow-y-auto">
            {watchlist.length === 0 ? (
              <div className="col-span-2 text-center py-12 text-slate-500 space-y-2">
                <ShieldCheck className="w-8 h-8 mx-auto opacity-40 text-emerald-400" />
                <p className="text-xs">No active watchlist entries.</p>
              </div>
            ) : (
              watchlist.map((entry) => (
                <div
                  key={entry.id}
                  className="p-3.5 rounded-xl bg-[#0B101D] border border-rose-500/20 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-white tracking-wider">
                      {entry.plate_raw || entry.plate_normalized || 'Unknown'}
                    </span>
                    <StatusBadge
                      variant={entry.severity === 'high' ? 'error' : 'warning'}
                      size="sm"
                    >
                      {entry.severity.toUpperCase()} SEVERITY
                    </StatusBadge>
                  </div>
                  <p className="text-xs text-slate-300">{entry.reason}</p>
                  {entry.expires_at && (
                    <p className="text-[10px] text-slate-500 font-mono">
                      Expires: {new Date(entry.expires_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* SECONDARY TAB: CAMPUS SCHEDULE                                      */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'schedule' && (
        <Card className="border-white/[0.08] bg-[#0E1322] space-y-4 p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Calendar className="w-5 h-5 text-emerald-400" />
              <div>
                <h3 className="text-sm font-bold text-slate-100">Campus Operating Schedule</h3>
                <p className="text-xs text-slate-400">Configured access windows and campus local timezone.</p>
              </div>
            </div>
            <div className="text-xs font-mono text-emerald-300 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
              Campus Time: {scheduleData?.current_local_time || 'Synchronizing...'}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {(scheduleData?.entries || []).map((entry) => (
              <div
                key={entry.weekday}
                className={`p-3.5 rounded-xl border space-y-1.5 ${
                  entry.is_open
                    ? 'bg-[#0B101D] border-white/[0.06]'
                    : 'bg-slate-900/40 border-white/[0.04] opacity-60'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-200 capitalize">{entry.weekday}</span>
                  <StatusBadge variant={entry.is_open ? 'success' : 'neutral'} size="sm">
                    {entry.is_open ? 'OPEN' : 'CLOSED'}
                  </StatusBadge>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {entry.is_open ? `${entry.open_time} – ${entry.close_time}` : 'Gate Restricted'}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* SECONDARY TAB: DIAGNOSTICS & EVIDENCE SNAPSHOTS                     */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'diagnostics' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-4">
              <div className="flex items-center gap-2.5">
                <Cpu className="w-5 h-5 text-cyan-400" />
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Compute Hardware Diagnostics</h3>
                  <p className="text-xs text-slate-400">ONNX Runtime execution providers & AI inference timing.</p>
                </div>
              </div>

              <div className="space-y-2 text-xs text-slate-300">
                <div className="flex justify-between p-2.5 rounded-lg bg-[#0B101D]">
                  <span className="text-slate-400">Execution Provider:</span>
                  <span className="font-mono text-cyan-300">{diagnostics?.recommendation.execution_provider || 'CPUExecutionProvider'}</span>
                </div>
                <div className="flex justify-between p-2.5 rounded-lg bg-[#0B101D]">
                  <span className="text-slate-400">GPU Device:</span>
                  <span className={diagnostics?.gpu.nvidia_smi.available ? 'text-emerald-400' : 'text-slate-400'}>
                    {diagnostics?.gpu.nvidia_smi.available ? 'NVIDIA RTX 4050' : 'CPU Execution'}
                  </span>
                </div>
                <div className="flex justify-between p-2.5 rounded-lg bg-[#0B101D]">
                  <span className="text-slate-400">InsightFace Model:</span>
                  <span className="text-emerald-400">{faceReady ? 'buffalo_l (Active)' : 'Unavailable'}</span>
                </div>
                <div className="flex justify-between p-2.5 rounded-lg bg-[#0B101D]">
                  <span className="text-slate-400">FastALPR OCR:</span>
                  <span className="text-amber-400">{alprReady ? 'Mobile-ViT (Active)' : 'Unavailable'}</span>
                </div>
              </div>
            </Card>

            <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-4">
              <div className="flex items-center gap-2.5">
                <Camera className="w-5 h-5 text-indigo-400" />
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Manual Evidence Capture</h3>
                  <p className="text-xs text-slate-400">Dual storage persistence: Supabase Storage and local disk.</p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="p-3.5 rounded-xl bg-[#0B101D] border border-white/[0.06] flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Instant Evidence Snapshot</div>
                    <div className="text-[11px] text-slate-400">Captures current camera frame for forensic audit.</div>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={takeSnapshot}
                    disabled={!isLive || isSavingSnapshot}
                    isLoading={isSavingSnapshot}
                    leftIcon={<Camera className="w-3.5 h-3.5" />}
                  >
                    Capture
                  </Button>
                </div>

                {snapshotMsg && (
                  <div className="text-xs text-emerald-400 font-medium flex items-center gap-1.5 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>{snapshotMsg}</span>
                  </div>
                )}

                {lastSavedStorage && (
                  <div className="p-3 rounded-xl bg-[#0B101D] border border-white/[0.04] text-[11px] space-y-1">
                    <div className="text-slate-400 font-mono">LATEST STORAGE TARGET:</div>
                    <div className="flex items-center gap-4">
                      <span className={`flex items-center gap-1 ${lastSavedStorage.remote_ok ? 'text-cyan-400' : 'text-slate-500'}`}>
                        <Cloud className="w-3.5 h-3.5" /> Supabase Storage: {lastSavedStorage.remote_ok ? 'Active' : 'Offline'}
                      </span>
                      <span className={`flex items-center gap-1 ${lastSavedStorage.local_ok ? 'text-amber-400' : 'text-slate-500'}`}>
                        <HardDrive className="w-3.5 h-3.5" /> Local Disk: {lastSavedStorage.local_ok ? 'Saved' : 'Offline'}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Deduplicated Recent Live Detections Feed */}
          <Card className="p-5 border-white/[0.08] bg-[#0E1322] space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Clock className="w-5 h-5 text-indigo-400" />
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Recent Live Camera Detections</h3>
                  <p className="text-xs text-slate-400">Deduplicated event stream from optical surveillance (8s cooldown).</p>
                </div>
              </div>
              <span className="text-xs font-mono bg-white/[0.06] text-slate-300 px-2.5 py-1 rounded-lg">
                {history.length} events
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[350px] overflow-y-auto">
              {history.length === 0 ? (
                <div className="col-span-2 text-center py-8 text-slate-500 text-xs">
                  No live camera detections recorded yet during this session.
                </div>
              ) : (
                history.map((item) => (
                  <div
                    key={item.id}
                    className="p-2.5 rounded-lg bg-[#0B101D] border border-white/[0.06] flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-6 h-6 rounded flex items-center justify-center ${item.type === 'face' ? 'bg-cyan-500/10 text-cyan-400' : 'bg-amber-500/10 text-amber-400'}`}>
                        {item.type === 'face' ? <ScanFace className="w-3.5 h-3.5" /> : <Car className="w-3.5 h-3.5" />}
                      </div>
                      <div>
                        <div className="font-semibold text-slate-200">{item.label}</div>
                        {item.subLabel && <div className="text-[10px] text-slate-400">{item.subLabel}</div>}
                      </div>
                    </div>
                    <div className="text-right">
                      <StatusBadge variant={item.status === 'matched' || item.status === 'registered' ? 'success' : 'neutral'} size="sm">
                        {item.status.toUpperCase()}
                      </StatusBadge>
                      <div className="text-[9px] font-mono text-slate-500 mt-0.5">{item.timestamp.toLocaleTimeString()}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

export default SecurityDashboard;
