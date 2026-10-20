// SmartGuard AI — Phase 5 Complete Visitor Management, QR Passes & Entry/Exit Lifecycle
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  QrCode,
  ShieldCheck,
  ShieldAlert,
  Users,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Camera,
  CameraOff,
  RefreshCw,
  Search,
  Plus,
  Send,
  Trash2,
  Printer,
  User,
  ArrowRight,
  Loader2,
  FileText,
  Check,
  Eye,
} from 'lucide-react';
import jsQR from 'jsqr';
import {
  visitorsApi,
  type VisitorPassResponse,
  type VisitorApprovalResponse,
  type VisitorMetrics,
  type VisitorPassCreatedResponse,
  type VisitorScanResponse,
  type CreateVisitorPassPayload,
} from '../../api/visitors';
import { peopleApi, type CampusPerson } from '../../api/phase2';
import { PageHeader } from '../../components/ui/PageHeader';
import { MetricCard } from '../../components/ui/MetricCard';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusBadge, type BadgeVariant } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';

type ActiveTab = 'scanner' | 'approvals' | 'active' | 'issue' | 'registry';

const STATUS_BADGES: Record<string, BadgeVariant> = {
  ISSUED: 'info',
  PENDING_APPROVAL: 'warning',
  ACTIVE_INSIDE: 'success',
  COMPLETED: 'neutral',
  EXPIRED: 'neutral',
  REVOKED: 'error',
  DENIED: 'error',
};

export default function VisitorManagement() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('scanner');
  const [metrics, setMetrics] = useState<VisitorMetrics | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  // ── Scanner State ──────────────────────────────────────────────────────────
  const [scanDirection, setScanDirection] = useState<'ENTRY' | 'EXIT'>('ENTRY');
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [scanProcessing, setScanProcessing] = useState(false);
  const [scanResult, setScanResult] = useState<VisitorScanResponse | null>(null);
  const [manualCode, setManualCode] = useState('');
  const [gateNotice, setGateNotice] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // ── Approvals Queue State ──────────────────────────────────────────────────
  const [approvals, setApprovals] = useState<VisitorApprovalResponse[]>([]);
  const [loadingApprovals, setLoadingApprovals] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState<VisitorApprovalResponse | null>(null);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [denialReason, setDenialReason] = useState('');
  const [showDenyModal, setShowDenyModal] = useState(false);
  const [approving, setApproving] = useState(false);

  // ── Active Visitors Inside State ───────────────────────────────────────────
  const [activeVisitors, setActiveVisitors] = useState<VisitorPassResponse[]>([]);
  const [loadingActive, setLoadingActive] = useState(false);

  // ── Pass Registry State ────────────────────────────────────────────────────
  const [passes, setPasses] = useState<VisitorPassResponse[]>([]);
  const [loadingPasses, setLoadingPasses] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [revokePassTarget, setRevokePassTarget] = useState<VisitorPassResponse | null>(null);
  const [revokeReason, setRevokeReason] = useState('');
  const [revoking, setRevoking] = useState(false);
  const [resendingEmailId, setResendingEmailId] = useState<string | null>(null);
  const [resendNotice, setResendNotice] = useState<string | null>(null);

  // ── Issue Pass Form State ──────────────────────────────────────────────────
  const [hosts, setHosts] = useState<CampusPerson[]>([]);
  const [formData, setFormData] = useState<CreateVisitorPassPayload>(() => {
    const now = new Date();
    const startStr = now.toISOString().slice(0, 16);
    const end = new Date(now.getTime() + 8 * 60 * 60 * 1000);
    const endStr = end.toISOString().slice(0, 16);
    return {
      full_name: '',
      phone: '',
      email: '',
      organization: '',
      host_id: '',
      vehicle_plate: '',
      purpose: 'Meeting / Campus Visit',
      valid_from: startStr,
      valid_until: endStr,
      send_email: true,
      notes: '',
    };
  });
  const [issuing, setIssuing] = useState(false);
  const [createdPass, setCreatedPass] = useState<VisitorPassCreatedResponse | null>(null);
  const [issueError, setIssueError] = useState<string | null>(null);

  // ── Load Initial Data ──────────────────────────────────────────────────────
  const loadMetrics = useCallback(async () => {
    try {
      setLoadingMetrics(true);
      const data = await visitorsApi.getMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load visitor metrics', err);
    } finally {
      setLoadingMetrics(false);
    }
  }, []);

  const loadApprovals = useCallback(async () => {
    try {
      setLoadingApprovals(true);
      const data = await visitorsApi.getPendingApprovals();
      setApprovals(data);
    } catch (err) {
      console.error('Failed to load pending approvals', err);
    } finally {
      setLoadingApprovals(false);
    }
  }, []);

  const loadActiveVisitors = useCallback(async () => {
    try {
      setLoadingActive(true);
      const data = await visitorsApi.getActiveInside();
      setActiveVisitors(data);
    } catch (err) {
      console.error('Failed to load active visitors', err);
    } finally {
      setLoadingActive(false);
    }
  }, []);

  const loadPasses = useCallback(async () => {
    try {
      setLoadingPasses(true);
      const filter = statusFilter === 'ALL' ? undefined : statusFilter;
      const data = await visitorsApi.getPasses({ status: filter, limit: 100 });
      setPasses(data);
    } catch (err) {
      console.error('Failed to load passes', err);
    } finally {
      setLoadingPasses(false);
    }
  }, [statusFilter]);

  const loadHosts = useCallback(async () => {
    try {
      const res = await peopleApi.list({ limit: 100 });
      // Filter campus people who can host (staff, faculty, student)
      const list = res.data.items || [];
      setHosts(list.filter((p) => p.person_type !== 'visitor'));
    } catch (err) {
      console.error('Failed to load campus hosts', err);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
    loadHosts();
  }, [loadMetrics, loadHosts]);

  useEffect(() => {
    if (activeTab === 'approvals') loadApprovals();
    if (activeTab === 'active') loadActiveVisitors();
    if (activeTab === 'registry') loadPasses();
  }, [activeTab, loadApprovals, loadActiveVisitors, loadPasses]);

  // Periodic metrics polling (every 10s)
  useEffect(() => {
    const timer = setInterval(() => {
      loadMetrics();
      if (activeTab === 'approvals') loadApprovals();
      if (activeTab === 'active') loadActiveVisitors();
    }, 10000);
    return () => clearInterval(timer);
  }, [activeTab, loadMetrics, loadApprovals, loadActiveVisitors]);

  // ── Camera Lifecycle ───────────────────────────────────────────────────────
  const stopCamera = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  const startCamera = async () => {
    try {
      setCameraError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.setAttribute('playsinline', 'true');
        await videoRef.current.play();
      }
      setCameraActive(true);
      requestAnimationFrame(tick);
    } catch (err) {
      console.error('Camera access denied or unavailable', err);
      setCameraError(
        'Unable to access camera. Please check browser permissions or use the manual credential scanner below.'
      );
      setCameraActive(false);
    }
  };

  const handleScanCredential = useCallback(
    async (credential: string) => {
      if (scanProcessing) return;
      setScanProcessing(true);
      setScanResult(null);
      setGateNotice(null);

      try {
        const res = await visitorsApi.scanPass({
          qr_credential: credential.trim(),
          direction: scanDirection,
        });

        setScanResult(res);

        if (res.gate_state === 'OPEN') {
          setGateNotice('GATE UNLOCKED — BARRIER RAISED FOR VISITOR ACCESS');
        } else if (res.status === 'PENDING_APPROVAL') {
          setGateNotice('GATE CLOSED — Awaiting explicit security officer authorization in pending approvals queue.');
          loadApprovals();
        } else {
          setGateNotice('GATE LOCKED — Access Denied');
        }

        loadMetrics();
      } catch (err: unknown) {
        console.error('Scan verification error', err);
        const errorMsg =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Verification failed. Invalid or unrecognized QR pass.';
        setScanResult({
          status: 'DENIED',
          message: String(errorMsg || 'Failed to verify pass'),
          direction: scanDirection,
          gate_state: 'CLOSED',
        });
        setGateNotice('GATE LOCKED — Access Denied');
      } finally {
        setScanProcessing(false);
      }
    },
    [scanProcessing, scanDirection, loadApprovals, loadMetrics]
  );

  const tick = useCallback(() => {
    if (!videoRef.current || !canvasRef.current || !streamRef.current) return;

    if (videoRef.current.readyState === videoRef.current.HAVE_ENOUGH_DATA) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });

      if (ctx) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(imageData.data, imageData.width, imageData.height, {
          inversionAttempts: 'dontInvert',
        });

        if (code && code.data) {
          // Detected QR code in frame!
          handleScanCredential(code.data);
          // Pause camera momentarily after successful detection
          stopCamera();
          return;
        }
      }
    }

    animationFrameRef.current = requestAnimationFrame(tick);
  }, [handleScanCredential, stopCamera]);

  // Clean up camera on tab switch or unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  useEffect(() => {
    if (activeTab !== 'scanner') {
      stopCamera();
    }
  }, [activeTab, stopCamera]);

  // ── Approval Decision Handlers ─────────────────────────────────────────────
  const handleApprove = async (approval: VisitorApprovalResponse) => {
    try {
      setApproving(true);
      await visitorsApi.decideApproval(approval.id, {
        decision: 'APPROVE',
        notes: approvalNotes.trim() || undefined,
      });
      setSelectedApproval(null);
      setApprovalNotes('');
      loadApprovals();
      loadMetrics();
      loadActiveVisitors();
    } catch (err: unknown) {
      console.error('Failed to approve visitor entry', err);
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to approve visitor entry';
      alert(`Approval error: ${detail}`);
    } finally {
      setApproving(false);
    }
  };

  const handleDeny = async () => {
    if (!selectedApproval || !denialReason.trim()) return;
    try {
      setApproving(true);
      await visitorsApi.decideApproval(selectedApproval.id, {
        decision: 'DENY',
        denial_reason: denialReason.trim(),
        notes: approvalNotes.trim() || undefined,
      });
      setShowDenyModal(false);
      setSelectedApproval(null);
      setDenialReason('');
      setApprovalNotes('');
      loadApprovals();
      loadMetrics();
    } catch (err: unknown) {
      console.error('Failed to deny visitor entry', err);
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to deny visitor entry';
      alert(`Denial error: ${detail}`);
    } finally {
      setApproving(false);
    }
  };

  // ── Exit from Active List ──────────────────────────────────────────────────
  const handleProcessExitFromActive = async (vpass: VisitorPassResponse) => {
    if (!confirm(`Confirm exit checkout for visitor ${vpass.visitor_name} (${vpass.pass_number})?`)) {
      return;
    }
    try {
      // Use pass number as lookup token if raw token unknown
      await visitorsApi.scanPass({
        qr_credential: `SGVP:${vpass.pass_number}`,
        direction: 'EXIT',
      });
      alert(`Exit processed successfully for ${vpass.visitor_name}. Gate unlocked.`);
      loadActiveVisitors();
      loadMetrics();
    } catch (err: unknown) {
      console.error('Exit checkout error', err);
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to process exit checkout';
      alert(`Exit error: ${detail}`);
    }
  };

  // ── Revoke Pass Handler ────────────────────────────────────────────────────
  const handleRevokePass = async () => {
    if (!revokePassTarget || !revokeReason.trim()) return;
    try {
      setRevoking(true);
      await visitorsApi.revokePass(revokePassTarget.id, { reason: revokeReason.trim() });
      setRevokePassTarget(null);
      setRevokeReason('');
      loadPasses();
      loadMetrics();
    } catch (err: unknown) {
      console.error('Failed to revoke pass', err);
      alert('Failed to revoke pass');
    } finally {
      setRevoking(false);
    }
  };

  // ── Resend Email Handler ───────────────────────────────────────────────────
  const handleResendEmail = async (vpass: VisitorPassResponse) => {
    try {
      setResendingEmailId(vpass.id);
      setResendNotice(null);
      const res = await visitorsApi.resendEmail(vpass.id);
      setResendNotice(`Email dispatch status for ${vpass.visitor_name}: ${res.status}`);
      loadPasses();
    } catch (err: unknown) {
      console.error('Resend email error', err);
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to resend pass email';
      alert(`Resend error: ${detail}`);
    } finally {
      setResendingEmailId(null);
    }
  };

  // ── Issue Pass Submit ──────────────────────────────────────────────────────
  const handleIssuePassSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIssueError(null);

    if (!formData.full_name?.trim()) {
      setIssueError('Visitor full name is required');
      return;
    }
    if (!formData.valid_from || !formData.valid_until) {
      setIssueError('Validity start and end times are required');
      return;
    }
    if (new Date(formData.valid_until) <= new Date(formData.valid_from)) {
      setIssueError('Valid Until must be later than Valid From');
      return;
    }

    try {
      setIssuing(true);
      const created = await visitorsApi.registerVisitor({
        ...formData,
        valid_from: new Date(formData.valid_from).toISOString(),
        valid_until: new Date(formData.valid_until).toISOString(),
      });
      setCreatedPass(created);
      loadMetrics();
      loadPasses();
    } catch (err: unknown) {
      console.error('Pass issuance failed', err);
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to issue visitor pass';
      setIssueError(String(detail));
    } finally {
      setIssuing(false);
    }
  };

  const handlePrintPass = () => {
    if (!createdPass) return;
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>SmartGuard AI — Visitor Pass ${createdPass.pass_number}</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 40px; color: #1e293b; }
            .badge { border: 2px solid #0f172a; border-radius: 12px; padding: 24px; max-width: 420px; margin: 0 auto; text-align: center; }
            .header { border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 16px; }
            .title { font-size: 20px; font-weight: bold; letter-spacing: 1px; color: #0f172a; }
            .subtitle { font-size: 11px; text-transform: uppercase; color: #64748b; letter-spacing: 2px; }
            .qr { margin: 16px 0; }
            .qr img { width: 200px; height: 200px; }
            .name { font-size: 22px; font-weight: bold; color: #0f172a; margin-top: 8px; }
            .detail { font-size: 13px; color: #475569; margin: 4px 0; }
            .footer { font-size: 10px; color: #94a3b8; margin-top: 16px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
          </style>
        </head>
        <body>
          <div class="badge">
            <div class="header">
              <div class="title">SMARTGUARD AI</div>
              <div class="subtitle">Campus Visitor Access Pass</div>
            </div>
            <div class="name">${createdPass.visitor_name}</div>
            <div class="detail"><strong>Pass #:</strong> ${createdPass.pass_number}</div>
            ${createdPass.organization ? `<div class="detail"><strong>Org:</strong> ${createdPass.organization}</div>` : ''}
            ${createdPass.host_name ? `<div class="detail"><strong>Host:</strong> ${createdPass.host_name}</div>` : ''}
            ${createdPass.vehicle_plate ? `<div class="detail"><strong>Vehicle:</strong> ${createdPass.vehicle_plate}</div>` : ''}
            <div class="qr">
              <img src="data:image/png;base64,${createdPass.qr_image_base64 || createdPass.qr_code_base64}" alt="QR Pass" />
            </div>
            <div class="detail"><strong>Valid From:</strong> ${new Date(createdPass.valid_from).toLocaleString()}</div>
            <div class="detail"><strong>Valid Until:</strong> ${new Date(createdPass.valid_until).toLocaleString()}</div>
            <div class="footer">
              Subject to security verification at campus checkpoint. Keep this credential ready for scanning upon entry and exit.
            </div>
          </div>
          <script>
            window.onload = function() { window.print(); }
          </script>
        </body>
      </html>
    `);
    printWindow.document.close();
  };

  // Filtered passes
  const filteredPasses = passes.filter((p) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.visitor_name.toLowerCase().includes(q) ||
      p.pass_number.toLowerCase().includes(q) ||
      (p.vehicle_plate && p.vehicle_plate.toLowerCase().includes(q)) ||
      (p.organization && p.organization.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <PageHeader
        title="Visitor Management & Secure QR Passes"
        description="Phase 5 — Full lifecycle visitor registration, high-entropy QR credentials, security gate approval, and entry/exit audit"
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadMetrics();
                if (activeTab === 'approvals') loadApprovals();
                if (activeTab === 'active') loadActiveVisitors();
                if (activeTab === 'registry') loadPasses();
              }}
              disabled={loadingMetrics}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loadingMetrics ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setActiveTab('issue')}
            >
              <Plus className="w-4 h-4 mr-2" />
              Issue New Pass
            </Button>
          </div>
        }
      />

      {/* ── Metrics Bar ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        <MetricCard
          title="Active Passes"
          value={metrics?.active_passes ?? '—'}
          icon={<QrCode className="w-4 h-4 text-sky-400" />}
          accentColor="sky"
          subtitle="Issued / Valid Passes"
        />
        <MetricCard
          title="Pending Approvals"
          value={metrics?.pending_approvals ?? '—'}
          icon={<ShieldAlert className="w-4 h-4 text-amber-400" />}
          accentColor="amber"
          subtitle="Officer Checkpoint Queue"
          badge={
            (metrics?.pending_approvals ?? 0) > 0 ? (
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
              </span>
            ) : undefined
          }
        />
        <MetricCard
          title="Inside Campus"
          value={metrics?.visitors_inside ?? '—'}
          icon={<Users className="w-4 h-4 text-emerald-400" />}
          accentColor="emerald"
          subtitle="Currently Active On-Site"
        />
        <MetricCard
          title="Completed Today"
          value={metrics?.completed_today ?? '—'}
          icon={<CheckCircle2 className="w-4 h-4 text-[#7565F5]" />}
          accentColor="violet"
          subtitle="Safely Exited Campus"
        />
        <MetricCard
          title="Revoked / Expired"
          value={metrics?.revoked_or_expired ?? '—'}
          icon={<AlertTriangle className="w-4 h-4 text-rose-400" />}
          accentColor="rose"
          subtitle="Invalidated / Closed"
        />
      </div>

      {/* ── Navigation Tabs ──────────────────────────────────────────────────── */}
      <div className="flex border-b border-white/[0.08] gap-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab('scanner')}
          className={`flex items-center gap-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'scanner'
              ? 'border-[#7565F5] text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Camera className="w-4 h-4" />
          QR Gate Scanner
        </button>

        <button
          onClick={() => setActiveTab('approvals')}
          className={`flex items-center gap-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors whitespace-nowrap relative ${
            activeTab === 'approvals'
              ? 'border-[#7565F5] text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          Pending Approvals
          {(metrics?.pending_approvals ?? 0) > 0 && (
            <span className="ml-1.5 px-2 py-0.5 text-xs font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
              {metrics?.pending_approvals}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('active')}
          className={`flex items-center gap-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'active'
              ? 'border-[#7565F5] text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Users className="w-4 h-4" />
          Active Inside ({metrics?.visitors_inside ?? 0})
        </button>

        <button
          onClick={() => setActiveTab('issue')}
          className={`flex items-center gap-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'issue'
              ? 'border-[#7565F5] text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Plus className="w-4 h-4" />
          Issue Pass
        </button>

        <button
          onClick={() => setActiveTab('registry')}
          className={`flex items-center gap-2 py-3 px-4 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
            activeTab === 'registry'
              ? 'border-[#7565F5] text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-4 h-4" />
          Pass Registry & History
        </button>
      </div>

      {/* ── TAB 1: QR Scanner & Gate ────────────────────────────────────────── */}
      {activeTab === 'scanner' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Scanner Viewport */}
          <div className="lg:col-span-7 space-y-4">
            <Card className="border-white/[0.08] bg-[#151C2C]/80 backdrop-blur-md overflow-hidden">
              <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <Camera className="w-5 h-5 text-sky-400" />
                  <CardTitle className="text-base font-semibold text-slate-100">
                    Live Checkpoint QR Scanner
                  </CardTitle>
                </div>

                {/* Direction Switcher */}
                <div className="flex items-center bg-[#0B0F19] rounded-lg p-1 border border-white/[0.08]">
                  <button
                    onClick={() => setScanDirection('ENTRY')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                      scanDirection === 'ENTRY'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    ENTRY SCAN
                  </button>
                  <button
                    onClick={() => setScanDirection('EXIT')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                      scanDirection === 'EXIT'
                        ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    EXIT SCAN
                  </button>
                </div>
              </CardHeader>

              <CardContent className="p-4 sm:p-6 space-y-4">
                {/* Camera View Area */}
                <div className="relative aspect-video bg-black/60 rounded-xl overflow-hidden border border-white/[0.08] flex items-center justify-center">
                  <video
                    ref={videoRef}
                    className={`w-full h-full object-cover ${cameraActive ? 'block' : 'hidden'}`}
                  />
                  <canvas ref={canvasRef} className="hidden" />

                  {/* Crosshair Target Box when camera active */}
                  {cameraActive && (
                    <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                      <div className="w-56 h-56 border-2 border-dashed border-sky-400/70 rounded-2xl relative animate-pulse shadow-lg shadow-sky-500/10">
                        <div className="absolute -top-1 -left-1 w-6 h-6 border-t-4 border-l-4 border-sky-400" />
                        <div className="absolute -top-1 -right-1 w-6 h-6 border-t-4 border-r-4 border-sky-400" />
                        <div className="absolute -bottom-1 -left-1 w-6 h-6 border-b-4 border-l-4 border-sky-400" />
                        <div className="absolute -bottom-1 -right-1 w-6 h-6 border-b-4 border-r-4 border-sky-400" />
                      </div>
                    </div>
                  )}

                  {/* Placeholder when camera inactive */}
                  {!cameraActive && (
                    <div className="text-center p-6 space-y-3">
                      <div className="w-14 h-14 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mx-auto text-slate-400">
                        <CameraOff className="w-7 h-7" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-200">Camera Inactive</p>
                        <p className="text-xs text-slate-400 mt-1">
                          Click below to activate device camera for live QR code scanning
                        </p>
                      </div>
                      <Button variant="primary" size="sm" onClick={startCamera}>
                        <Camera className="w-4 h-4 mr-2" />
                        Start Camera
                      </Button>
                    </div>
                  )}

                  {/* Processing indicator */}
                  {scanProcessing && (
                    <div className="absolute inset-0 bg-black/75 flex flex-col items-center justify-center text-white space-y-2">
                      <Loader2 className="w-8 h-8 animate-spin text-sky-400" />
                      <p className="text-sm font-medium">Validating Pass Credential...</p>
                    </div>
                  )}
                </div>

                {cameraActive && (
                  <div className="flex justify-between items-center pt-2">
                    <span className="text-xs text-slate-400 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      Live Camera Streaming — Point at visitor's QR code
                    </span>
                    <Button variant="outline" size="sm" onClick={stopCamera}>
                      <CameraOff className="w-4 h-4 mr-2" />
                      Stop Camera
                    </Button>
                  </div>
                )}

                {cameraError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-300">
                    {cameraError}
                  </div>
                )}

                {/* Handheld / Manual Input Alternative */}
                <div className="pt-3 border-t border-white/[0.06] space-y-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    Manual Credential / Handheld Scanner Input
                  </span>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Paste QR payload or raw token (e.g. SGVP:...)"
                      value={manualCode}
                      onChange={(e) => setManualCode(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && manualCode.trim()) {
                          handleScanCredential(manualCode);
                        }
                      }}
                      className="flex-1 bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5]"
                    />
                    <Button
                      variant="primary"
                      onClick={() => handleScanCredential(manualCode)}
                      disabled={!manualCode.trim() || scanProcessing}
                    >
                      Verify
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Verification Result & Simulated Gate Status */}
          <div className="lg:col-span-5 space-y-4">
            {/* Gate Barrier State Card */}
            <Card className="border-white/[0.08] bg-[#151C2C]/80">
              <CardHeader className="pb-3 border-b border-white/[0.06]">
                <CardTitle className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                  Simulated Physical Gate Status
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 sm:p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">Barrier Actuator:</span>
                  <span
                    className={`font-mono text-sm px-3 py-1 rounded-md font-bold ${
                      scanResult?.gate_state === 'OPEN'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    }`}
                  >
                    {scanResult?.gate_state === 'OPEN' ? 'OPEN / UNLOCKED' : 'CLOSED / LOCKED'}
                  </span>
                </div>

                {gateNotice && (
                  <div
                    className={`p-3 rounded-lg text-xs font-medium border ${
                      scanResult?.gate_state === 'OPEN'
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : scanResult?.status === 'PENDING_APPROVAL'
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                        : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    }`}
                  >
                    {gateNotice}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Scan Result Feedback */}
            {scanResult ? (
              <Card
                className={`border ${
                  scanResult.status === 'PENDING_APPROVAL'
                    ? 'border-amber-500/30 bg-amber-500/[0.03]'
                    : scanResult.status === 'ACTIVE_INSIDE' || scanResult.status === 'COMPLETED'
                    ? 'border-emerald-500/30 bg-emerald-500/[0.03]'
                    : 'border-rose-500/30 bg-rose-500/[0.03]'
                }`}
              >
                <CardHeader className="pb-3 border-b border-white/[0.06]">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold text-slate-100 flex items-center gap-2">
                      {scanResult.status === 'PENDING_APPROVAL' && (
                        <ShieldAlert className="w-5 h-5 text-amber-400" />
                      )}
                      {scanResult.status === 'COMPLETED' && (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      )}
                      {scanResult.status === 'DENIED' && (
                        <XCircle className="w-5 h-5 text-rose-400" />
                      )}
                      Scan Result: {scanResult.status.replace('_', ' ')}
                    </CardTitle>
                    <StatusBadge
                      variant={
                        scanResult.status === 'PENDING_APPROVAL'
                          ? 'warning'
                          : scanResult.status === 'COMPLETED'
                          ? 'success'
                          : 'error'
                      }
                      size="sm"
                    >
                      {scanResult.direction}
                    </StatusBadge>
                  </div>
                </CardHeader>

                <CardContent className="p-4 space-y-4">
                  <div className="space-y-2 text-sm">
                    {scanResult.visitor_name && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">Visitor:</span>
                        <span className="font-semibold text-slate-200">
                          {scanResult.visitor_name}
                        </span>
                      </div>
                    )}
                    {scanResult.pass_number && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">Pass Number:</span>
                        <span className="font-mono text-xs text-sky-400">
                          {scanResult.pass_number}
                        </span>
                      </div>
                    )}
                    <div className="pt-2 text-xs text-slate-300 bg-white/[0.03] p-3 rounded-lg border border-white/[0.06]">
                      {scanResult.message}
                    </div>
                  </div>

                  {scanResult.status === 'PENDING_APPROVAL' && (
                    <Button
                      variant="primary"
                      className="w-full"
                      onClick={() => {
                        setActiveTab('approvals');
                        loadApprovals();
                      }}
                    >
                      <ShieldCheck className="w-4 h-4 mr-2" />
                      Go to Pending Approvals Queue
                    </Button>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card className="border-white/[0.08] bg-[#151C2C]/50 p-6 text-center text-slate-400 space-y-2">
                <QrCode className="w-8 h-8 mx-auto text-slate-500" />
                <p className="text-sm font-medium">Awaiting QR scan</p>
                <p className="text-xs text-slate-500">
                  Scan a QR pass or type a credential to trigger checkpoint validation.
                </p>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ── TAB 2: Pending Approvals Queue ─────────────────────────────────── */}
      {activeTab === 'approvals' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-slate-200">
                Security Officer Entry Approval Queue
              </h3>
              <p className="text-xs text-slate-400">
                Mandatory checkpoint authorization. A valid QR scan alerts security and requires explicit officer decision before the gate opens.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadApprovals}
              disabled={loadingApprovals}
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loadingApprovals ? 'animate-spin' : ''}`} />
              Refresh Queue
            </Button>
          </div>

          {loadingApprovals ? (
            <div className="p-12 text-center text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-sky-400 mb-2" />
              Loading pending approvals...
            </div>
          ) : approvals.length === 0 ? (
            <Card className="border-white/[0.08] bg-[#151C2C]/50 p-8 text-center text-slate-400 space-y-2">
              <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400" />
              <p className="text-sm font-medium text-slate-200">Approval Queue Clear</p>
              <p className="text-xs text-slate-500">
                No visitor passes are currently awaiting checkpoint authorization.
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {approvals.map((req) => (
                <Card
                  key={req.id}
                  className="border-white/[0.08] bg-[#151C2C] hover:border-white/[0.15] transition-colors"
                >
                  <CardHeader className="pb-3 border-b border-white/[0.06] flex flex-row items-center justify-between">
                    <div>
                      <div className="font-semibold text-slate-100 flex items-center gap-2">
                        <User className="w-4 h-4 text-sky-400" />
                        {req.visitor_name}
                      </div>
                      <div className="font-mono text-xs text-slate-400 mt-0.5">
                        {req.pass_number}
                      </div>
                    </div>
                    <StatusBadge variant="warning" size="sm">
                      AWAITING APPROVAL
                    </StatusBadge>
                  </CardHeader>

                  <CardContent className="p-4 space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-2 text-slate-300">
                      <div>
                        <span className="text-slate-500 block">Host:</span>
                        <span className="font-medium">{req.host_name || 'N/A'}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Vehicle:</span>
                        <span className="font-mono font-medium">{req.vehicle_plate || 'None'}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Organization:</span>
                        <span>{req.organization || 'External Guest'}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Purpose:</span>
                        <span>{req.purpose || 'Campus Visit'}</span>
                      </div>
                    </div>

                    <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-slate-400">
                      <span>Scanned: {new Date(req.scanned_at).toLocaleTimeString()}</span>
                      <span className="text-emerald-400 font-medium">
                        Schedule: {req.schedule_status || 'Open'}
                      </span>
                    </div>

                    {/* Actions */}
                    <div className="pt-3 border-t border-white/[0.06] flex items-center gap-2">
                      <Button
                        variant="primary"
                        size="sm"
                        className="flex-1 bg-emerald-600 hover:bg-emerald-500"
                        onClick={() => handleApprove(req)}
                        disabled={approving}
                      >
                        <Check className="w-4 h-4 mr-1.5" />
                        Approve Entry
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-rose-400 hover:bg-rose-500/10 border-rose-500/30"
                        onClick={() => {
                          setSelectedApproval(req);
                          setShowDenyModal(true);
                        }}
                        disabled={approving}
                      >
                        <XCircle className="w-4 h-4 mr-1.5" />
                        Deny
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── TAB 3: Active Visitors Inside ──────────────────────────────────── */}
      {activeTab === 'active' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-slate-200">
                Visitors Currently Inside Campus
              </h3>
              <p className="text-xs text-slate-400">
                Live list of guests who have checked in through security. Exits can be processed through the QR scanner or direct checkout.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadActiveVisitors}
              disabled={loadingActive}
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loadingActive ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>

          {loadingActive ? (
            <div className="p-12 text-center text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-sky-400 mb-2" />
              Loading active visitors...
            </div>
          ) : activeVisitors.length === 0 ? (
            <Card className="border-white/[0.08] bg-[#151C2C]/50 p-8 text-center text-slate-400 space-y-2">
              <Users className="w-8 h-8 mx-auto text-slate-500" />
              <p className="text-sm font-medium text-slate-200">No Visitors Inside Campus</p>
              <p className="text-xs text-slate-500">
                All approved visitor visits for today have completed exit or none have entered.
              </p>
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#151C2C]">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#0B0F19] text-slate-400 font-semibold border-b border-white/[0.08]">
                  <tr>
                    <th className="py-3 px-4">Visitor</th>
                    <th className="py-3 px-4">Pass #</th>
                    <th className="py-3 px-4">Host</th>
                    <th className="py-3 px-4">Vehicle</th>
                    <th className="py-3 px-4">Check-in Time</th>
                    <th className="py-3 px-4">Duration Inside</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06] text-slate-300">
                  {activeVisitors.map((v) => {
                    const checkIn = v.check_in_at ? new Date(v.check_in_at) : null;
                    const minsInside = checkIn
                      ? Math.floor((Date.now() - checkIn.getTime()) / 60000)
                      : 0;
                    return (
                      <tr key={v.id} className="hover:bg-white/[0.02]">
                        <td className="py-3 px-4">
                          <div className="font-semibold text-slate-100">{v.visitor_name}</div>
                          {v.organization && (
                            <div className="text-slate-500 text-[11px]">{v.organization}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono text-sky-400">{v.pass_number}</td>
                        <td className="py-3 px-4">{v.host_name || '—'}</td>
                        <td className="py-3 px-4 font-mono">{v.vehicle_plate || '—'}</td>
                        <td className="py-3 px-4">{checkIn ? checkIn.toLocaleTimeString() : '—'}</td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 font-mono">
                            {minsInside < 60
                              ? `${minsInside}m`
                              : `${Math.floor(minsInside / 60)}h ${minsInside % 60}m`}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-xs"
                            onClick={() => handleProcessExitFromActive(v)}
                          >
                            <ArrowRight className="w-3.5 h-3.5 mr-1" />
                            Process Exit
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 4: Issue Visitor Pass ──────────────────────────────────────── */}
      {activeTab === 'issue' && (
        <div className="max-w-2xl mx-auto">
          <Card className="border-white/[0.08] bg-[#151C2C]">
            <CardHeader className="pb-3 border-b border-white/[0.06]">
              <CardTitle className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <Plus className="w-5 h-5 text-sky-400" />
                Pre-Register Visitor & Issue High-Entropy QR Pass
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <form onSubmit={handleIssuePassSubmit} className="space-y-4">
                {issueError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-300">
                    {issueError}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Full Name *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Jane Doe"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Email Address
                    </label>
                    <input
                      type="email"
                      placeholder="jane@example.com"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Phone Number
                    </label>
                    <input
                      type="tel"
                      placeholder="+91 9876543210"
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Organization / Company
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Acme Tech Solutions"
                      value={formData.organization}
                      onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Campus Host / Contact
                    </label>
                    <select
                      value={formData.host_id || ''}
                      onChange={(e) => setFormData({ ...formData, host_id: e.target.value || undefined })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    >
                      <option value="">-- No Host / General Campus Access --</option>
                      {hosts.map((h) => (
                        <option key={h.id} value={h.id}>
                          {h.full_name} ({h.department || h.person_type})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Vehicle Plate (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. MH02AB1234"
                      value={formData.vehicle_plate}
                      onChange={(e) => setFormData({ ...formData, vehicle_plate: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Valid From *
                    </label>
                    <input
                      type="datetime-local"
                      required
                      value={formData.valid_from}
                      onChange={(e) => setFormData({ ...formData, valid_from: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                      Valid Until *
                    </label>
                    <input
                      type="datetime-local"
                      required
                      value={formData.valid_until}
                      onChange={(e) => setFormData({ ...formData, valid_until: e.target.value })}
                      className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                    Purpose of Visit
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Vendor delivery, Campus interview, Guest lecture"
                    value={formData.purpose}
                    onChange={(e) => setFormData({ ...formData, purpose: e.target.value })}
                    className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#7565F5]"
                  />
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox"
                    id="send_email"
                    checked={formData.send_email}
                    onChange={(e) => setFormData({ ...formData, send_email: e.target.checked })}
                    className="rounded border-white/[0.2] bg-[#0B0F19] text-[#7565F5] focus:ring-0"
                  />
                  <label htmlFor="send_email" className="text-xs text-slate-300 cursor-pointer">
                    Dispatch QR Pass via Brevo Email Gateway (Phase 4 integration)
                  </label>
                </div>

                <div className="pt-4 border-t border-white/[0.06] flex justify-end gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setActiveTab('registry')}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={issuing}>
                    {issuing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Generating Pass...
                      </>
                    ) : (
                      <>
                        <QrCode className="w-4 h-4 mr-2" />
                        Issue Secure Pass
                      </>
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 5: Pass Registry & History ─────────────────────────────────── */}
      {activeTab === 'registry' && (
        <div className="space-y-4">
          {/* Notification feedback */}
          {resendNotice && (
            <div className="p-3 bg-sky-500/10 border border-sky-500/20 rounded-lg text-xs text-sky-300 flex justify-between items-center">
              <span>{resendNotice}</span>
              <button onClick={() => setResendNotice(null)} className="text-slate-400 hover:text-white">
                ✕
              </button>
            </div>
          )}

          {/* Search & Filters */}
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
            <div className="relative w-full sm:w-80">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search visitor, pass #, vehicle..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#151C2C] border border-white/[0.12] rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-[#151C2C] border border-white/[0.12] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-[#7565F5]"
              >
                <option value="ALL">All Statuses</option>
                <option value="ISSUED">Issued / Active</option>
                <option value="PENDING_APPROVAL">Pending Approval</option>
                <option value="ACTIVE_INSIDE">Inside Campus</option>
                <option value="COMPLETED">Completed</option>
                <option value="REVOKED">Revoked</option>
                <option value="DENIED">Denied</option>
              </select>

              <Button
                variant="outline"
                size="sm"
                onClick={loadPasses}
                disabled={loadingPasses}
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingPasses ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>

          {/* Table */}
          {loadingPasses ? (
            <div className="p-12 text-center text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-sky-400 mb-2" />
              Loading pass registry...
            </div>
          ) : filteredPasses.length === 0 ? (
            <Card className="border-white/[0.08] bg-[#151C2C]/50 p-8 text-center text-slate-400 space-y-2">
              <FileText className="w-8 h-8 mx-auto text-slate-500" />
              <p className="text-sm font-medium text-slate-200">No Visitor Passes Found</p>
              <p className="text-xs text-slate-500">
                Adjust search query or filter, or issue a new visitor pass.
              </p>
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#151C2C]">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#0B0F19] text-slate-400 font-semibold border-b border-white/[0.08]">
                  <tr>
                    <th className="py-3 px-4">Pass #</th>
                    <th className="py-3 px-4">Visitor</th>
                    <th className="py-3 px-4">Host</th>
                    <th className="py-3 px-4">Validity Window</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Email</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06] text-slate-300">
                  {filteredPasses.map((p) => (
                    <tr key={p.id} className="hover:bg-white/[0.02]">
                      <td className="py-3 px-4 font-mono font-medium text-sky-400">
                        {p.pass_number}
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-100">{p.visitor_name}</div>
                        <div className="text-slate-500 text-[11px]">{p.visitor_email || p.visitor_phone || '—'}</div>
                      </td>
                      <td className="py-3 px-4">{p.host_name || '—'}</td>
                      <td className="py-3 px-4 text-[11px] text-slate-400">
                        <div>{new Date(p.valid_from).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</div>
                        <div>to {new Date(p.valid_until).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</div>
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge variant={STATUS_BADGES[p.status] || 'neutral'} size="sm">
                          {p.status.replace('_', ' ')}
                        </StatusBadge>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                            p.email_delivery_status === 'SENT'
                              ? 'bg-emerald-500/10 text-emerald-400'
                              : p.email_delivery_status === 'FAILED'
                              ? 'bg-rose-500/10 text-rose-400'
                              : 'bg-slate-500/10 text-slate-400'
                          }`}
                        >
                          {p.email_delivery_status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right space-x-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-sky-400 border-sky-500/30 hover:bg-sky-500/10 text-[11px] px-2 py-1"
                          title="View QR Code & Badge"
                          onClick={() => setCreatedPass(p as unknown as VisitorPassCreatedResponse)}
                        >
                          <Eye className="w-3 h-3" />
                        </Button>
                        {p.visitor_email && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-[11px] px-2 py-1"
                            title="Resend Pass via Brevo Email"
                            disabled={resendingEmailId === p.id}
                            onClick={() => handleResendEmail(p)}
                          >
                            <Send className="w-3 h-3" />
                          </Button>
                        )}
                        {p.status === 'ISSUED' && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-rose-400 border-rose-500/30 hover:bg-rose-500/10 text-[11px] px-2 py-1"
                            title="Revoke Pass"
                            onClick={() => setRevokePassTarget(p)}
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── MODAL: Pass Issued Successfully (with QR Code) ─────────────────── */}
      {createdPass && (
        <Modal
          isOpen={true}
          onClose={() => setCreatedPass(null)}
          title="Visitor Pass Issued Successfully"
        >
          <div className="space-y-4 text-center">
            <div className="p-4 bg-white rounded-xl inline-block shadow-lg mx-auto">
              <img
                src={`data:image/png;base64,${createdPass.qr_image_base64 || createdPass.qr_code_base64}`}
                alt="Visitor Pass QR"
                className="w-48 h-48 mx-auto"
              />
            </div>

            <div>
              <p className="text-lg font-bold text-slate-100">{createdPass.visitor_name}</p>
              <p className="font-mono text-sm text-sky-400 font-semibold">
                Pass #: {createdPass.pass_number}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Valid: {new Date(createdPass.valid_from).toLocaleString()} — {new Date(createdPass.valid_until).toLocaleString()}
              </p>
            </div>

            <div className="p-3 bg-[#0B0F19] rounded-lg text-xs text-slate-300 border border-white/[0.08] text-left space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-500">Email Delivery:</span>
                <span
                  className={
                    createdPass.email_delivery_status === 'SENT'
                      ? 'text-emerald-400 font-medium'
                      : 'text-amber-400 font-medium'
                  }
                >
                  {createdPass.email_delivery_status}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Security Requirement:</span>
                <span className="text-slate-200">Mandatory officer approval upon scan</span>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={handlePrintPass}>
                <Printer className="w-4 h-4 mr-2" />
                Print Pass Badge
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                onClick={() => {
                  setCreatedPass(null);
                  setActiveTab('registry');
                }}
              >
                Done
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── MODAL: Deny Entry Reason ────────────────────────────────────────── */}
      {showDenyModal && selectedApproval && (
        <Modal
          isOpen={true}
          onClose={() => {
            setShowDenyModal(false);
            setSelectedApproval(null);
          }}
          title={`Deny Entry: ${selectedApproval.visitor_name}`}
        >
          <div className="space-y-4">
            <p className="text-xs text-slate-400">
              Please enter the security justification for denying campus entry. The gate will remain closed and an audit record will be logged.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                Denial Reason *
              </label>
              <textarea
                required
                rows={3}
                placeholder="e.g. Failure to produce valid government photo ID, host unavailable, or security restriction."
                value={denialReason}
                onChange={(e) => setDenialReason(e.target.value)}
                className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowDenyModal(false);
                  setSelectedApproval(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                className="bg-rose-600 hover:bg-rose-500"
                onClick={handleDeny}
                disabled={!denialReason.trim() || approving}
              >
                Confirm Denial
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── MODAL: Revoke Pass ──────────────────────────────────────────────── */}
      {revokePassTarget && (
        <Modal
          isOpen={true}
          onClose={() => setRevokePassTarget(null)}
          title={`Revoke Pass: ${revokePassTarget.pass_number}`}
        >
          <div className="space-y-4">
            <p className="text-xs text-slate-400">
              Revoking this pass will invalidate the QR credential immediately. Any subsequent scan attempt will trigger a security alert.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">
                Revocation Reason *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. Visitor cancelled visit, or security concern."
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                className="w-full bg-[#0B0F19] border border-white/[0.12] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setRevokePassTarget(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                className="bg-rose-600 hover:bg-rose-500"
                onClick={handleRevokePass}
                disabled={!revokeReason.trim() || revoking}
              >
                Confirm Revocation
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
