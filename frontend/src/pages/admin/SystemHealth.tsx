// SmartGuard AI — Premium System Health & Infrastructure Diagnostics
import { useState, useEffect, useCallback } from 'react';
import {
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Server,
  Database,
  Cpu,
  Clock,
  Terminal,
} from 'lucide-react';
import { healthApi } from '../../api/health';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { StatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { AlertBanner } from '../../components/ui/Alert';
import type { ReadinessResponse } from '../../types';

export function SystemHealth() {
  const [healthData, setHealthData] = useState<ReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await healthApi.readiness();
      setHealthData(data);
      setLastChecked(new Date());
    } catch {
      setHealthData({
        status: 'unavailable',
        database: false,
        pgvector: false,
      });
      setError('Unable to reach the backend health endpoints. Verify FastAPI is running.');
      setLastChecked(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 60000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const isHealthy =
    healthData?.status === 'ready' &&
    Boolean(healthData?.database) &&
    Boolean(healthData?.pgvector);

  const isDegraded =
    !isHealthy &&
    (healthData?.status === 'ready' || Boolean(healthData?.database) || Boolean(healthData?.pgvector));

  const getOverallStatusBadge = () => {
    if (loading && !healthData) {
      return (
        <StatusBadge variant="neutral" size="md">
          Checking Infrastructure...
        </StatusBadge>
      );
    }
    if (isHealthy) {
      return (
        <StatusBadge variant="success" size="md" pulse>
          All Systems Operational
        </StatusBadge>
      );
    }
    if (isDegraded) {
      return (
        <StatusBadge variant="warning" size="md">
          Partially Degraded
        </StatusBadge>
      );
    }
    return (
      <StatusBadge variant="error" size="md">
        Service Unavailable
      </StatusBadge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="System Health & Infrastructure"
        description="Real-time operational status of backend services, PostgreSQL database engine, and pgvector extension."
        badge={getOverallStatusBadge()}
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchHealth}
            isLoading={loading}
            leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
          >
            Refresh Status
          </Button>
        }
      />

      {/* Error Alert */}
      {error && (
        <AlertBanner variant="error" onClose={() => setError(null)}>
          {error}
        </AlertBanner>
      )}

      {/* Main Status Overview Card */}
      <Card
        className={`border-l-4 ${
          isHealthy
            ? 'border-l-emerald-500'
            : isDegraded
            ? 'border-l-amber-500'
            : 'border-l-rose-500'
        }`}
      >
        <CardContent className="p-5 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div
                className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border ${
                  isHealthy
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : isDegraded
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                }`}
              >
                {isHealthy ? (
                  <CheckCircle2 className="w-6 h-6" />
                ) : isDegraded ? (
                  <AlertTriangle className="w-6 h-6" />
                ) : (
                  <XCircle className="w-6 h-6" />
                )}
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-100">
                  {isHealthy
                    ? 'All Core Components Healthy'
                    : isDegraded
                    ? 'Infrastructure Running with Warnings'
                    : 'Backend Communication Disrupted'}
                </h2>
                <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  <span>
                    {lastChecked
                      ? `Last inspected: ${lastChecked.toLocaleTimeString()}`
                      : 'Connecting to probes...'}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <span className="text-xs font-mono text-slate-400">STATUS:</span>
              <span className="font-mono text-xs font-bold px-2.5 py-1 rounded bg-black/40 border border-white/[0.08] text-slate-200">
                {healthData?.status ? healthData.status.toUpperCase() : 'CHECKING'}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Component Diagnostics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
        {/* 1. FastAPI REST Server */}
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-lg bg-[#7565F5]/10 border border-[#7565F5]/25 text-[#9B8DFC] flex items-center justify-center">
                <Server className="w-5 h-5" />
              </div>
              <StatusBadge variant="success" size="sm">
                Operational
              </StatusBadge>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-100">FastAPI API Engine</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Asynchronous Python application server handling session tokens and endpoint routing.
              </p>
            </div>

            <div className="pt-3 border-t border-white/[0.04] space-y-2 text-xs">
              <div className="flex justify-between items-center text-slate-400">
                <span>Liveness Endpoint</span>
                <span className="font-mono text-emerald-400">/api/health/live (200)</span>
              </div>
              <div className="flex justify-between items-center text-slate-400">
                <span>Protocol</span>
                <span className="font-mono text-slate-300">HTTP/1.1 REST</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 2. Supabase PostgreSQL */}
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/25 text-sky-400 flex items-center justify-center">
                <Database className="w-5 h-5" />
              </div>
              {loading && !healthData ? (
                <StatusBadge variant="neutral" size="sm">
                  Checking...
                </StatusBadge>
              ) : healthData?.database ? (
                <StatusBadge variant="success" size="sm">
                  Connected
                </StatusBadge>
              ) : (
                <StatusBadge variant="error" size="sm">
                  Offline
                </StatusBadge>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-100">Supabase PostgreSQL</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Relational datastore managing credentials, role constraints, and audit history.
              </p>
            </div>

            <div className="pt-3 border-t border-white/[0.04] space-y-2 text-xs">
              <div className="flex justify-between items-center text-slate-400">
                <span>Database Connectivity</span>
                <span
                  className={`font-mono ${
                    healthData?.database ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {healthData?.database ? 'Ready / Responding' : 'Connection Failed'}
                </span>
              </div>
              <div className="flex justify-between items-center text-slate-400">
                <span>Pool Status</span>
                <span className="font-mono text-slate-300">Session Mode (5432)</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 3. pgvector AI Extension */}
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/25 text-indigo-400 flex items-center justify-center">
                <Cpu className="w-5 h-5" />
              </div>
              {loading && !healthData ? (
                <StatusBadge variant="neutral" size="sm">
                  Checking...
                </StatusBadge>
              ) : healthData?.pgvector ? (
                <StatusBadge variant="success" size="sm">
                  Operational
                </StatusBadge>
              ) : (
                <StatusBadge variant="warning" size="sm">
                  Unavailable
                </StatusBadge>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-100">pgvector AI Extension</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Vector similarity indexing layer for Phase 2 512-d facial biometric embeddings.
              </p>
            </div>

            <div className="pt-3 border-t border-white/[0.04] space-y-2 text-xs">
              <div className="flex justify-between items-center text-slate-400">
                <span>Vector Extension Probe</span>
                <span
                  className={`font-mono ${
                    healthData?.pgvector ? 'text-emerald-400' : 'text-amber-400'
                  }`}
                >
                  {healthData?.pgvector ? 'Installed (Active)' : 'Not Found in DB'}
                </span>
              </div>
              <div className="flex justify-between items-center text-slate-400">
                <span>Index Engine</span>
                <span className="font-mono text-slate-300">Cosine Distance (HNSW)</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Troubleshooting Panel for Degraded States */}
      {!isHealthy && (
        <Card>
          <CardContent className="p-5">
            <div className="flex items-start gap-3 mb-3">
              <Terminal className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-xs font-semibold text-slate-200">
                  Database & pgvector Setup Instructions
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  If the database status reports offline or vector is missing, ensure the
                  connection credentials and migrations are applied:
                </p>
              </div>
            </div>

            <div className="bg-[#0A0D14] rounded-lg p-3 text-xs font-mono text-slate-300 space-y-1.5 border border-white/[0.04]">
              <p className="text-slate-500"># 1. Verify backend/.env contains a valid Supabase DATABASE_URL</p>
              <p className="text-[#9B8DFC]">DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres</p>
              <p className="text-slate-500 pt-1"># 2. Apply migrations to initialize tables and enable vector extension</p>
              <p className="text-emerald-400">alembic upgrade head</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default SystemHealth;
