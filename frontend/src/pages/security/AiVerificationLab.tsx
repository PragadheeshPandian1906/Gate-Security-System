// SmartGuard AI — AI Verification Lab (Phase 2)
// Face recognition + ALPR test interface with diagnostics
import { useState, useEffect, useRef } from 'react';
import {
  ScanFace, Car, Cpu, Upload, CheckCircle2, AlertCircle,
  Loader2, X, Zap, Activity, HardDrive, Eye,
  Clock, AlertTriangle, Monitor, Cloud,
} from 'lucide-react';
import { aiApi, type FaceVerifyResult, type AlprVerifyResult, type AiDiagnostics } from '../../api/phase2';
import { getErrorMessage } from '../../api/client';

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = 'face' | 'alpr' | 'diagnostics';

// ── Storage Status Badge ───────────────────────────────────────────────────────

function StorageStatusBadge({ storage }: { storage: { local_ok: boolean; remote_ok: boolean; storage_path?: string | null } | null }) {
  if (!storage) return null;
  return (
    <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-xs">
      <div className="flex items-center gap-2 text-slate-300">
        <HardDrive size={13} className="text-slate-400" />
        <span>Local Disk:</span>
        <span className={storage.local_ok ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
          {storage.local_ok ? '✓ Stored' : '✗ Failed'}
        </span>
      </div>
      <div className="flex items-center gap-2 text-slate-300">
        <Cloud size={13} className={storage.remote_ok ? 'text-cyan-400' : 'text-slate-500'} />
        <span>Supabase Cloud:</span>
        <span className={storage.remote_ok ? 'text-cyan-400 font-semibold flex items-center gap-1' : 'text-slate-500'}>
          {storage.remote_ok ? '✓ Uploaded' : '— Not Synced'}
        </span>
      </div>
    </div>
  );
}

// ── Confidence Bar ────────────────────────────────────────────────────────────

function ConfidenceBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const color = pct >= 70 ? 'bg-emerald-400' : pct >= 45 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="text-white font-mono">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── Image Drop Zone ───────────────────────────────────────────────────────────

function DropZone({
  file, onFile, accept = 'image/*', label = 'Drop or click to upload image',
}: {
  file: File | null;
  onFile: (f: File) => void;
  accept?: string;
  label?: string;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const preview = file ? URL.createObjectURL(file) : null;

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`relative cursor-pointer rounded-2xl border-2 border-dashed transition-all overflow-hidden
        ${dragging ? 'border-cyan-400 bg-cyan-400/5' : preview ? 'border-slate-600' : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/30'}
      `}
      style={{ minHeight: '220px' }}
    >
      {preview ? (
        <img src={preview} alt="Upload preview" className="w-full h-56 object-cover" />
      ) : (
        <div className="flex flex-col items-center justify-center py-14 gap-3">
          <div className="p-4 rounded-2xl bg-slate-800 text-slate-400">
            <Upload size={32} />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-slate-300">{label}</p>
            <p className="text-xs text-slate-500 mt-1">JPEG, PNG, WebP — max 10 MB</p>
          </div>
        </div>
      )}
      <input ref={inputRef} type="file" className="sr-only" accept={accept} onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
    </div>
  );
}

// ── Result Tag ────────────────────────────────────────────────────────────────

function ResultTag({ result }: { result: string }) {
  const map: Record<string, { label: string; color: string; icon: React.ElementType }> = {
    matched:        { label: 'MATCHED',        color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', icon: CheckCircle2 },
    no_match:       { label: 'NO MATCH',        color: 'bg-slate-700 text-slate-300 border-slate-600',             icon: X },
    low_confidence: { label: 'LOW CONFIDENCE',  color: 'bg-amber-500/20 text-amber-400 border-amber-500/30',       icon: AlertTriangle },
    no_face:        { label: 'NO FACE',         color: 'bg-slate-700 text-slate-300 border-slate-600',             icon: Eye },
    no_plate:       { label: 'NO PLATE',        color: 'bg-slate-700 text-slate-300 border-slate-600',             icon: Eye },
    error:          { label: 'ERROR',           color: 'bg-red-500/20 text-red-400 border-red-500/30',             icon: AlertCircle },
  };
  const m = map[result] ?? map.error;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border uppercase tracking-wider ${m.color}`}>
      <Icon size={12} /> {m.label}
    </span>
  );
}

// ── Face Verification Panel ───────────────────────────────────────────────────

function FaceVerifyPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FaceVerifyResult | null>(null);
  const [history, setHistory] = useState<Array<{ id: string; result: string; confidence: number | null; matched_person_id: string | null; timestamp: string }>>([]);

  useEffect(() => {
    aiApi.getFaceHistory(10).then(r => setHistory(r.data)).catch(() => {});
  }, [result]);

  const run = async () => {
    if (!file) return;
    setLoading(true); setResult(null);
    try {
      const res = await aiApi.verifyFace(file);
      setResult(res.data);
    } catch (err) {
      setResult({
        result: 'error', confidence: null, distance: null, matched_person: null,
        faces_detected: 0, candidates: [], verification_id: null, storage: null,
        error: getErrorMessage(err),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Left: Input */}
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <ScanFace size={18} className="text-cyan-400" /> Face Recognition Test
        </h3>
        <DropZone file={file} onFile={f => { setFile(f); setResult(null); }} label="Drop face image here" />
        <button
          onClick={run}
          disabled={!file || loading}
          className="w-full flex items-center justify-center gap-2 py-3 bg-cyan-500 hover:bg-cyan-400 text-slate-900 font-bold rounded-xl transition-all disabled:opacity-40 hover:shadow-lg hover:shadow-cyan-500/20"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
          {loading ? 'Analysing…' : 'Run Face Verification'}
        </button>
        {file && (
          <button onClick={() => { setFile(null); setResult(null); }}
            className="w-full text-xs text-slate-500 hover:text-slate-300 transition-colors">
            Clear image
          </button>
        )}
      </div>

      {/* Right: Result */}
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white">Result</h3>

        {!result && !loading && (
          <div className="h-56 flex flex-col items-center justify-center text-slate-600 rounded-2xl bg-slate-800/30 border border-slate-700/50">
            <ScanFace size={40} className="mb-3" />
            <p className="text-sm">Upload an image and run verification</p>
          </div>
        )}

        {loading && (
          <div className="h-56 flex flex-col items-center justify-center gap-3 rounded-2xl bg-slate-800/30 border border-slate-700/50">
            <Loader2 size={32} className="animate-spin text-cyan-400" />
            <p className="text-sm text-slate-400">Running InsightFace inference…</p>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
              <div className="flex items-center justify-between">
                <ResultTag result={result.result} />
                <span className="text-xs text-slate-500">{result.faces_detected} face(s) detected</span>
              </div>

              {result.matched_person && (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                  <div className="w-10 h-10 rounded-full bg-emerald-400/10 flex items-center justify-center text-emerald-400 font-bold text-lg">
                    {result.matched_person.name?.charAt(0) ?? '?'}
                  </div>
                  <div>
                    <p className="font-semibold text-white">{result.matched_person.name}</p>
                    <p className="text-xs text-slate-400 font-mono">{result.matched_person.id}</p>
                  </div>
                </div>
              )}

              {result.confidence !== null && (
                <ConfidenceBar value={result.confidence} label="Confidence" />
              )}
              {result.distance !== null && (
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Cosine Distance</span>
                  <span className="font-mono text-white">{result.distance.toFixed(4)}</span>
                </div>
              )}
              {result.error && (
                <p className="text-xs text-red-400 bg-red-400/5 border border-red-400/10 rounded-lg p-2">{result.error}</p>
              )}
            </div>

            {result.candidates.length > 1 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Top Candidates</p>
                {result.candidates.slice(0, 3).map((c, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800 border border-slate-700">
                    <span className="text-sm text-slate-200">{c.person_name}</span>
                    <span className="text-xs font-mono text-cyan-400">{(c.confidence * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}

            {result.storage && (
              <StorageStatusBadge storage={result.storage} />
            )}
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Clock size={11} /> Recent History
            </p>
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {history.map(h => (
                <div key={h.id} className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-800/60">
                  <ResultTag result={h.result} />
                  <span className="text-xs text-slate-500 font-mono">
                    {new Date(h.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ALPR Panel ────────────────────────────────────────────────────────────────

function AlprPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AlprVerifyResult | null>(null);
  const [history, setHistory] = useState<Array<{ id: string; result: string; detected_plate: string | null; timestamp: string }>>([]);

  useEffect(() => {
    aiApi.getAlprHistory(10).then(r => setHistory(r.data)).catch(() => {});
  }, [result]);

  const run = async () => {
    if (!file) return;
    setLoading(true); setResult(null);
    try {
      const res = await aiApi.verifyPlate(file);
      setResult(res.data);
    } catch (err) {
      setResult({
        result: 'error', detected_plate: null, detected_plate_normalized: null,
        detection_confidence: null, ocr_confidence: null, vehicle_match: null,
        all_plates: [], verification_id: null, storage: null, error: getErrorMessage(err),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-6">
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <Car size={18} className="text-blue-400" /> License Plate Recognition
        </h3>
        <DropZone file={file} onFile={f => { setFile(f); setResult(null); }} label="Drop vehicle image here" />
        <button
          onClick={run}
          disabled={!file || loading}
          className="w-full flex items-center justify-center gap-2 py-3 bg-blue-500 hover:bg-blue-400 text-white font-bold rounded-xl transition-all disabled:opacity-40 hover:shadow-lg hover:shadow-blue-500/20"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
          {loading ? 'Analysing…' : 'Run ALPR'}
        </button>
        {file && (
          <button onClick={() => { setFile(null); setResult(null); }}
            className="w-full text-xs text-slate-500 hover:text-slate-300 transition-colors">
            Clear image
          </button>
        )}
      </div>

      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white">Result</h3>

        {!result && !loading && (
          <div className="h-56 flex flex-col items-center justify-center text-slate-600 rounded-2xl bg-slate-800/30 border border-slate-700/50">
            <Car size={40} className="mb-3" />
            <p className="text-sm">Upload a vehicle image and run ALPR</p>
          </div>
        )}

        {loading && (
          <div className="h-56 flex flex-col items-center justify-center gap-3 rounded-2xl bg-slate-800/30 border border-slate-700/50">
            <Loader2 size={32} className="animate-spin text-blue-400" />
            <p className="text-sm text-slate-400">Running FastALPR inference…</p>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
              <ResultTag result={result.result} />

              {result.detected_plate && (
                <div className="flex items-center justify-between">
                  <span className="font-mono text-2xl font-bold text-white tracking-widest bg-slate-700 px-4 py-2 rounded-lg">
                    {result.detected_plate}
                  </span>
                  <span className="text-xs font-mono text-slate-400">{result.detected_plate_normalized}</span>
                </div>
              )}

              {result.detection_confidence !== null && (
                <ConfidenceBar value={result.detection_confidence} label="Detection Confidence" />
              )}
              {result.ocr_confidence !== null && (
                <ConfidenceBar value={result.ocr_confidence} label="OCR Confidence" />
              )}

              {result.vehicle_match && (
                <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                  <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Registered Vehicle</p>
                  <p className="font-semibold text-white">
                    {[result.vehicle_match.color, result.vehicle_match.make, result.vehicle_match.model].filter(Boolean).join(' ')}
                  </p>
                  {result.vehicle_match.owner_name && (
                    <p className="text-xs text-slate-400">Owner: {result.vehicle_match.owner_name}</p>
                  )}
                  <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium
                    ${result.vehicle_match.vehicle_status === 'flagged' ? 'bg-red-400/10 text-red-400' : 'bg-emerald-400/10 text-emerald-400'}`}>
                    {result.vehicle_match.vehicle_status?.toUpperCase()}
                  </span>
                </div>
              )}

              {result.error && (
                <p className="text-xs text-red-400 bg-red-400/5 border border-red-400/10 rounded-lg p-2">{result.error}</p>
              )}
            </div>

            {result.all_plates.length > 1 && (
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-400 uppercase">All Detected Plates</p>
                {result.all_plates.map((p, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800 border border-slate-700">
                    <span className="font-mono text-white font-bold">{p.text}</span>
                    <span className="text-xs font-mono text-blue-400">{(p.ocr_confidence * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}

            {result.storage && (
              <StorageStatusBadge storage={result.storage} />
            )}
          </div>
        )}

        {history.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Clock size={11} /> Recent History
            </p>
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {history.map(h => (
                <div key={h.id} className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-800/60">
                  <div className="flex items-center gap-2">
                    <ResultTag result={h.result} />
                    {h.detected_plate && (
                      <span className="font-mono text-xs text-white">{h.detected_plate}</span>
                    )}
                  </div>
                  <span className="text-xs text-slate-500 font-mono">{new Date(h.timestamp).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Diagnostics Panel ─────────────────────────────────────────────────────────

function DiagnosticsPanel() {
  const [diag, setDiag] = useState<AiDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    aiApi.getDiagnostics()
      .then(r => setDiag(r.data))
      .catch(e => setError(getErrorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 size={28} className="animate-spin text-cyan-400" />
    </div>
  );
  if (error) return (
    <div className="flex items-center gap-2 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400">
      <AlertCircle size={16} /> {error}
    </div>
  );
  if (!diag) return null;

  const StatusDot = ({ ok }: { ok: boolean }) => (
    <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
  );

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* GPU & Compute */}
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <Monitor size={18} className="text-purple-400" /> Compute & GPU
        </h3>

        <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Device</span>
            <span className={`font-bold text-sm ${diag.recommendation.compute_device === 'GPU' ? 'text-green-400' : 'text-amber-400'}`}>
              {diag.recommendation.compute_device}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Execution Provider</span>
            <span className="text-xs font-mono text-slate-300 bg-slate-700 px-2 py-0.5 rounded">
              {diag.recommendation.execution_provider}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">NVIDIA GPU</span>
            <div className="flex items-center gap-2">
              <StatusDot ok={diag.gpu.nvidia_smi.available} />
              <span className="text-xs text-slate-300">
                {diag.gpu.nvidia_smi.gpus?.[0]?.name ?? (diag.gpu.nvidia_smi.available ? 'Detected' : 'Not found')}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">CUDA (via torch)</span>
            <div className="flex items-center gap-2">
              <StatusDot ok={diag.gpu.torch.cuda_available} />
              <span className="text-xs text-slate-300">{diag.gpu.torch.cuda_device_name ?? 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
          <p className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Cpu size={14} className="text-cyan-400" /> ONNX Runtime
          </p>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Available</span>
            <StatusDot ok={diag.onnxruntime.available} />
          </div>
          {diag.onnxruntime.version && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-300">Version</span>
              <span className="text-xs font-mono text-white">{diag.onnxruntime.version}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">CUDA Provider</span>
            <StatusDot ok={diag.onnxruntime.cuda_provider ?? false} />
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            {diag.onnxruntime.providers?.map(p => (
              <span key={p} className="text-xs font-mono bg-slate-700 text-slate-300 px-2 py-0.5 rounded">{p}</span>
            ))}
          </div>
        </div>
      </div>

      {/* AI Models */}
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" /> AI Models Status
        </h3>

        <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
          <p className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <ScanFace size={14} className="text-cyan-400" /> InsightFace
          </p>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Installed</span>
            <StatusDot ok={diag.insightface.available} />
          </div>
          {diag.insightface.version && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-300">Version</span>
              <span className="text-xs font-mono text-white">{diag.insightface.version}</span>
            </div>
          )}
          {diag.insightface.cached_models && (
            <div>
              <span className="text-xs text-slate-400">Cached Models: </span>
              <span className="text-xs text-white">{diag.insightface.cached_models.join(', ') || 'None'}</span>
            </div>
          )}
          {diag.insightface.error && (
            <p className="text-xs text-red-400">{diag.insightface.error}</p>
          )}
        </div>

        <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
          <p className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Car size={14} className="text-blue-400" /> FastALPR
          </p>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Installed</span>
            <StatusDot ok={diag.fast_alpr.available} />
          </div>
          {diag.fast_alpr.version && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-300">Version</span>
              <span className="text-xs font-mono text-white">{diag.fast_alpr.version}</span>
            </div>
          )}
          {diag.fast_alpr.error && (
            <p className="text-xs text-red-400">{diag.fast_alpr.error}</p>
          )}
        </div>

        <div className="p-4 rounded-xl bg-slate-800 border border-slate-700 space-y-3">
          <p className="text-sm font-semibold text-slate-200">Pipeline Readiness</p>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">Face Recognition</span>
            <div className="flex items-center gap-2">
              <StatusDot ok={diag.recommendation.face_recognition_ready} />
              <span className="text-xs">{diag.recommendation.face_recognition_ready ? 'Ready' : 'Not ready'}</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">ALPR</span>
            <div className="flex items-center gap-2">
              <StatusDot ok={diag.recommendation.alpr_ready} />
              <span className="text-xs">{diag.recommendation.alpr_ready ? 'Ready' : 'Not ready'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function AiVerificationLab() {
  const [tab, setTab] = useState<Tab>('face');

  const tabs: Array<{ id: Tab; label: string; icon: React.ElementType; color: string }> = [
    { id: 'face',        label: 'Face Recognition', icon: ScanFace, color: 'text-cyan-400' },
    { id: 'alpr',        label: 'License Plate',     icon: Car,      color: 'text-blue-400' },
    { id: 'diagnostics', label: 'AI Diagnostics',    icon: Cpu,      color: 'text-purple-400' },
  ];

  return (
    <div className="flex flex-col gap-6 p-6 min-h-full">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 text-cyan-400">
            <Zap size={24} />
          </div>
          AI Verification Lab
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Test InsightFace face recognition and FastALPR license plate detection pipelines
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex items-center gap-1 p-1 bg-slate-800 rounded-xl border border-slate-700 w-fit">
        {tabs.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-slate-700 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon size={15} className={active ? t.color : ''} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-2xl p-6">
        {tab === 'face' && <FaceVerifyPanel />}
        {tab === 'alpr' && <AlprPanel />}
        {tab === 'diagnostics' && <DiagnosticsPanel />}
      </div>
    </div>
  );
}
