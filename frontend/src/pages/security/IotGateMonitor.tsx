// SmartGuard AI — Minimal IoT Gate Controller Monitoring Dashboard
// Primary Purpose: Real-time observation and troubleshooting of backend <-> ESP32 WebSocket communication.
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  Wifi,
  WifiOff,
  RotateCcw,
  ShieldCheck,
  Radio,
  Cpu,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  Terminal,
  Lock,
  Unlock,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  gateApi,
  type IotControllerStatus,
  type IotSystemEvent,
} from '../../api/phase3';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';

export function IotGateMonitor() {
  const { token } = useAuth();

  // Connection & Controller state
  const [iotStatus, setIotStatus] = useState<IotControllerStatus | null>(null);
  const [isWsConnected, setIsWsConnected] = useState<boolean>(false);
  const [events, setEvents] = useState<IotSystemEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Reset operation state
  const [showConfirmReset, setShowConfirmReset] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [resetFeedback, setResetFeedback] = useState<{
    type: 'success' | 'warning' | 'error';
    message: string;
    detail?: string;
  } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const isWsConnectedRef = useRef<boolean>(false);
  const isFetchingRef = useRef<boolean>(false);

  // Fallback REST fetch
  const fetchRestSnapshot = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const [statusRes, eventsRes] = await Promise.all([
        gateApi.getIotStatus(),
        gateApi.getIotEvents(),
      ]);
      setIotStatus(statusRes.data);
      setEvents(eventsRes.data);
    } catch (err) {
      console.warn('Failed to load REST snapshot for IoT controller', err);
    } finally {
      isFetchingRef.current = false;
      setLoading(false);
    }
  }, []);

  // Real-time WebSocket connection to backend
  useEffect(() => {
    fetchRestSnapshot();

    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use backend host (port 8000 in dev)
    const host = window.location.hostname;
    const wsUrl = `${protocol}//${host}:8000/ws/gate/monitor?token=${encodeURIComponent(token)}`;

    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connectWs = () => {
      try {
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          isWsConnectedRef.current = true;
          setIsWsConnected(true);
        };

        ws.onmessage = (msgEvent) => {
          try {
            const data = JSON.parse(msgEvent.data);
            if (data.type === 'INIT') {
              if (data.status) setIotStatus(data.status);
              if (data.events) setEvents(data.events);
            } else if (data.type === 'STATUS_UPDATE') {
              if (data.status) setIotStatus(data.status);
            } else if (data.type === 'EVENT') {
              const newEv: IotSystemEvent = data.data;
              setEvents((prev) => [newEv, ...prev].slice(0, 100));
            }
          } catch (e) {
            console.error('Failed to parse WebSocket message', e);
          }
        };

        ws.onclose = () => {
          isWsConnectedRef.current = false;
          setIsWsConnected(false);
          // Try reconnecting after 4 seconds
          reconnectTimeout = setTimeout(connectWs, 4000);
        };

        ws.onerror = () => {
          isWsConnectedRef.current = false;
          setIsWsConnected(false);
        };
      } catch (err) {
        console.warn('WebSocket connection error', err);
      }
    };

    connectWs();

    // Periodic keepalive / status sync interval
    const pollInterval = setInterval(() => {
      if (!isWsConnectedRef.current) {
        fetchRestSnapshot();
      }
    }, 10000);

    return () => {
      clearInterval(pollInterval);
      clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [token, fetchRestSnapshot]);

  // Handle Reset Gate Action
  const handleExecuteReset = async () => {
    setShowConfirmReset(false);
    setIsResetting(true);
    setResetFeedback(null);

    try {
      const res = await gateApi.reset();
      const hw = res.data.hardware;

      if (hw && hw.acknowledged) {
        setResetFeedback({
          type: 'success',
          message: 'Controller acknowledged the close command',
          detail: 'The gate position is not independently verified; no position sensor is configured.',
        });
      } else if (hw && hw.delivered && hw.status === 'REJECTED') {
        setResetFeedback({
          type: 'warning',
          message: res.data.message,
          detail: 'Use Manual Close to release an active manual-open latch.',
        });
      } else if (hw && hw.delivered) {
        setResetFeedback({
          type: 'warning',
          message: 'Close command delivered; controller acknowledgement is unavailable',
          detail: hw.error || 'The controller acknowledgement timed out.',
        });
      } else {
        setResetFeedback({
          type: 'warning',
          message: 'Close command failed; gate state was not changed',
          detail: hw?.error || 'The controller is disconnected or the service is unavailable.',
        });
      }

      // Refresh snapshot
      await fetchRestSnapshot();
    } catch (err: any) {
      setResetFeedback({
        type: 'error',
        message: 'Request failed',
        detail: err.response?.data?.detail || err.message || 'Unable to communicate with backend.',
      });
    } finally {
      setIsResetting(false);
    }
  };

  // Handle Manual Open Gate Action
  const handleOpenGate = async () => {
    setIsResetting(true);
    setResetFeedback(null);
    try {
      const response = await gateApi.open();
      const hardware = response.data.hardware;
      setResetFeedback(hardware.controller_acknowledged
        ? {
            type: 'success',
            message: 'Controller acknowledged manual-open latch',
            detail: 'Gate remains latched until Manual Close. Position is not independently sensor-verified.',
          }
        : hardware.delivered
        ? {
            type: 'warning',
            message: 'Open command delivered; controller acknowledgement is unavailable',
            detail: hardware.error || 'The controller acknowledgement timed out.',
          }
        : {
            type: 'error',
            message: 'Open command was not delivered',
            detail: hardware.error || 'The controller is disconnected or the service is unavailable.',
          });
      await fetchRestSnapshot();
    } catch (err: any) {
      setResetFeedback({
        type: 'error',
        message: 'Failed to open gate',
        detail: err.response?.data?.detail || err.message,
      });
    } finally {
      setIsResetting(false);
    }
  };

  // Handle Manual Close Gate Action
  const handleCloseGate = async () => {
    setIsResetting(true);
    setResetFeedback(null);
    try {
      const response = await gateApi.close();
      const hardware = response.data.hardware;
      setResetFeedback(hardware.controller_acknowledged
        ? {
            type: 'success',
            message: 'Controller acknowledged Manual Close',
            detail: 'Controller reports CLOSED; position is not independently sensor-verified.',
          }
        : hardware.delivered
        ? {
            type: 'warning',
            message: 'Close command delivered; controller acknowledgement is unavailable',
            detail: hardware.error || 'The controller acknowledgement timed out.',
          }
        : {
            type: 'error',
            message: 'Close command was not delivered',
            detail: hardware.error || 'The controller is disconnected or the service is unavailable.',
          });
      await fetchRestSnapshot();
    } catch (err: any) {
      setResetFeedback({
        type: 'error',
        message: 'Failed to close gate',
        detail: err.response?.data?.detail || err.message,
      });
    } finally {
      setIsResetting(false);
    }
  };

  // Severity color mapping for events
  const getSeverityBadge = (level: string) => {
    switch (level) {
      case 'SUCCESS':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800/60">SUCCESS</span>;
      case 'WARNING':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-800/60">WARN</span>;
      case 'ERROR':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-800/60">ERROR</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">INFO</span>;
    }
  };

  const isEspConnected = Boolean(iotStatus?.is_connected);
  const isHealthy = Boolean(iotStatus?.is_healthy);

  return (
    <div className="space-y-6">
      <PageHeader
        title="IoT Gate Controller Monitor"
        description="ESP32 controller telemetry and authenticated gate commands through the backend"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchRestSnapshot}
              isLoading={loading}
              leftIcon={<RotateCcw className="w-4 h-4" />}
            >
              Refresh
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleOpenGate}
              disabled={isResetting}
              leftIcon={<Unlock className="w-4 h-4 text-emerald-400" />}
              className="bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border-emerald-500/30 text-xs font-bold"
            >
              Open Gate
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCloseGate}
              disabled={isResetting}
              leftIcon={<Lock className="w-4 h-4 text-rose-400" />}
              className="bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border-rose-500/30 text-xs font-bold"
            >
              Close Gate
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setShowConfirmReset(true)}
              disabled={isResetting}
              isLoading={isResetting}
              leftIcon={<RotateCcw className="w-4 h-4" />}
            >
              Reset Gate
            </Button>
          </div>
        }
      />

      {/* Reset Feedback Notification */}
      {resetFeedback && (
        <div
          className={`p-4 rounded-xl border flex items-start gap-3 transition-all ${
            resetFeedback.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : resetFeedback.type === 'warning'
              ? 'bg-amber-950/40 border-amber-800/60 text-amber-300'
              : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
          }`}
        >
          {resetFeedback.type === 'success' && <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-400 mt-0.5" />}
          {resetFeedback.type === 'warning' && <AlertTriangle className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />}
          {resetFeedback.type === 'error' && <XCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />}
          <div className="flex-1">
            <p className="font-semibold text-sm">{resetFeedback.message}</p>
            {resetFeedback.detail && <p className="text-xs opacity-90 mt-1">{resetFeedback.detail}</p>}
          </div>
          <button
            onClick={() => setResetFeedback(null)}
            className="text-xs opacity-60 hover:opacity-100 text-slate-400"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Section A: Connection & Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: ESP32 Hardware Status */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase">
                ESP32 Controller
              </span>
              {isEspConnected ? (
                <Wifi className="w-5 h-5 text-emerald-400" />
              ) : (
                <WifiOff className="w-5 h-5 text-rose-400" />
              )}
            </div>
            <div className="flex items-baseline gap-2">
              <span className={`text-xl font-bold ${isEspConnected ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isEspConnected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-400 space-y-1">
              <p>ID: <span className="font-mono text-slate-200">{iotStatus?.device_id || 'N/A'}</span></p>
              <p>IP: <span className="font-mono text-slate-200">{iotStatus?.client_ip || 'Offline'}</span></p>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Backend WebSocket Bridge */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase">
                Backend Telemetry WS
              </span>
              <Radio className={`w-5 h-5 ${isWsConnected ? 'text-cyan-400 animate-pulse' : 'text-slate-600'}`} />
            </div>
            <div className="flex items-baseline gap-2">
              <span className={`text-xl font-bold ${isWsConnected ? 'text-cyan-400' : 'text-amber-400'}`}>
                {isWsConnected ? 'STREAMING' : 'POLLING'}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-400 space-y-1">
              <p>Channel: <span className="font-mono text-slate-200">/ws/gate/monitor</span></p>
              <p>Mode: <span className="text-slate-200">{isWsConnected ? 'Bidirectional Live' : 'REST Fallback'}</span></p>
            </div>
          </CardContent>
        </Card>

        {/* Card 3: Last Heartbeat */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase">
                Last Heartbeat
              </span>
              <Clock className="w-5 h-5 text-indigo-400" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-slate-100">
                {iotStatus?.heartbeat_age_seconds != null
                  ? `${iotStatus.heartbeat_age_seconds}s ago`
                  : 'No heartbeat'}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-400 space-y-1">
              <p>Watchdog: <span className="text-slate-200">{isHealthy ? 'Healthy (< 30s)' : 'Inactive / Timeout'}</span></p>
              <p>Interval: <span className="text-slate-200">10 seconds</span></p>
            </div>
          </CardContent>
        </Card>

        {/* Card 4: Commanded Gate State */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase">
                Controller-reported State
              </span>
              <Activity className="w-5 h-5 text-amber-400" />
            </div>
            <div className="flex items-baseline gap-2">
              <span
                className={`text-xl font-bold ${
                  iotStatus?.reported_gate_state === 'OPEN'
                    ? 'text-emerald-400'
                    : iotStatus?.reported_gate_state === 'CLOSED'
                    ? 'text-sky-400'
                    : 'text-amber-400'
                }`}
              >
                {iotStatus?.reported_gate_state || 'UNKNOWN'}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-400 space-y-1">
              <p>Controller report only; no independent position sensor is configured.</p>
              <p>
                Mode:{' '}
                <span className="text-slate-200">
                  {iotStatus?.reported_gate_mode === 'MANUAL_LATCHED_OPEN'
                    ? 'MANUAL LATCHED — waits for Manual Close'
                    : iotStatus?.reported_gate_mode || 'UNKNOWN'}
                </span>
              </p>
              {iotStatus?.reported_gate_mode !== 'MANUAL_LATCHED_OPEN' && (
                <p>Automated auto-close: <span className="text-slate-200">15000 ms</span></p>
              )}
              <p className="text-[11px] text-slate-500">Controller-commanded position</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Section B & D Layout: Live System Messages & Device Info */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 Cols): Live System Messages Event Log */}
        <div className="lg:col-span-2">
          <Card className="bg-slate-900 border-slate-800 flex flex-col h-[520px]">
            <CardHeader className="border-b border-slate-800/80 pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  Live System Event Log
                </CardTitle>
                <span className="text-xs font-mono text-slate-500">
                  {events.length} events (latest 100 max)
                </span>
              </div>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-0 font-mono text-xs divide-y divide-slate-800/60">
              {events.length === 0 ? (
                <div className="p-8 text-center text-slate-500">
                  No system events recorded yet. Connect ESP32 or trigger a gate operation.
                </div>
              ) : (
                events.map((ev) => (
                  <div key={ev.id} className="p-3 hover:bg-slate-800/40 transition-colors flex items-start gap-3">
                    <span className="text-slate-500 shrink-0 text-[11px] pt-0.5">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                    <div className="shrink-0">{getSeverityBadge(ev.level)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-semibold text-slate-300 text-[11px]">
                          [{ev.source}] {ev.event_type}
                        </span>
                      </div>
                      <p className="text-slate-200 break-words">{ev.message}</p>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column (1 Col): Device Hardware & Emergency Reset */}
        <div className="space-y-6">
          {/* Section D: Informational Device Specification Panel */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800/80 pb-3">
              <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-indigo-400" />
                Hardware Specifications
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Device ID</span>
                <span className="font-mono text-slate-200">smartguard-esp32-01</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Microcontroller</span>
                <span className="text-slate-200">ESP32 WROOM-32 (Xtensa Dual-Core)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Gate Actuator</span>
                <span className="text-slate-200">SG90 Servo (PWM GPIO 18)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Display Module</span>
                <span className="text-slate-200">16×2 LCD with I2C (GPIO 21/22 @ 0x27)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Protocol</span>
                <span className="text-slate-200">JSON over WebSocket (LAN)</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Auto-Close Safety</span>
                <span className="text-slate-200">5.0s (ESP32 Millis Timer)</span>
              </div>
            </CardContent>
          </Card>

          {/* Section C: Manual Reset Card */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800/80 pb-3">
              <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Gate Override Control
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <p className="text-xs text-slate-400 leading-relaxed">
                Reset sends an authorized reset command. If the controller is manually latched
                open, use Manual Close to release the latch; reset cannot override that mode.
              </p>

              <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800 text-[11px] text-slate-400 flex items-start gap-2">
                <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                <span>
                  Acknowledgement from the ESP32 confirms receipt and servo PWM command, not
                  physical position limit feedback.
                </span>
              </div>

              <Button
                variant="danger"
                className="w-full justify-center"
                onClick={() => setShowConfirmReset(true)}
                disabled={isResetting}
                isLoading={isResetting}
                leftIcon={<RotateCcw className="w-4 h-4" />}
              >
                Reset Gate to Closed
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Confirmation Modal for Reset Gate */}
      {showConfirmReset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <AlertTriangle className="w-6 h-6 shrink-0" />
              <h3 className="text-lg font-bold text-slate-100">Confirm Gate Reset</h3>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">
              Are you sure you want to command the physical gate controller and backend simulation
              to reset to <span className="font-semibold text-rose-400">CLOSED</span>?
            </p>
            <p className="text-xs text-slate-400">
              This will immediately command the SG90 servo to 0° and cancel any pending auto-close timers.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowConfirmReset(false)}
                disabled={isResetting}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleExecuteReset}
                disabled={isResetting}
                isLoading={isResetting}
                leftIcon={<RotateCcw className="w-4 h-4" />}
              >
                Confirm & Close Gate
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default IotGateMonitor;
