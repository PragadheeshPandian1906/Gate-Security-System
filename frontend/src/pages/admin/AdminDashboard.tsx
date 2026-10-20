// SmartGuard AI — Premium Security Operations Center (Admin Overview)
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  UserCheck,
  UserX,
  Activity,
  ArrowRight,
  Database,
  Cpu,
  Server,
  ShieldCheck,
  UserPlus,
  ShieldAlert,
  FileText,
  Calendar,
  Mail,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { healthApi } from '../../api/health';
import { accountsApi } from '../../api/accounts';
import { PageHeader } from '../../components/ui/PageHeader';
import { MetricCard } from '../../components/ui/MetricCard';
import { StatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../../components/ui/Table';
import { UserAvatar } from '../../components/ui/States';
import type { ReadinessResponse, Account } from '../../types';

export function AdminDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [health, setHealth] = useState<ReadinessResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [totalAccounts, setTotalAccounts] = useState<number>(0);
  const [activeCount, setActiveCount] = useState<number>(0);
  const [inactiveCount, setInactiveCount] = useState<number>(0);
  const [accountsLoading, setAccountsLoading] = useState(true);

  useEffect(() => {
    // Fetch system health
    setHealthLoading(true);
    healthApi
      .readiness()
      .then((data) => {
        setHealth(data);
      })
      .catch(() => {
        setHealth({ status: 'unavailable', database: false, pgvector: false });
      })
      .finally(() => {
        setHealthLoading(false);
      });

    // Fetch account stats
    setAccountsLoading(true);
    accountsApi
      .list({ limit: 10 })
      .then((data) => {
        setAccounts(data.accounts || []);
        setTotalAccounts(data.total || data.accounts.length);
        const active = data.accounts.filter((a) => a.status === 'active').length;
        const inactive = data.accounts.filter((a) => a.status === 'inactive').length;
        setActiveCount(active);
        setInactiveCount(inactive);
      })
      .catch(() => {
        setAccounts([]);
      })
      .finally(() => {
        setAccountsLoading(false);
      });
  }, []);

  const isHealthy = health?.status === 'ready' && health?.database && health?.pgvector;

  const getSystemStatusBadge = () => {
    if (healthLoading) {
      return (
        <StatusBadge variant="neutral" size="sm">
          Checking...
        </StatusBadge>
      );
    }
    if (isHealthy) {
      return (
        <StatusBadge variant="success" size="sm" pulse>
          Operational
        </StatusBadge>
      );
    }
    if (health?.status === 'ready' || health?.database) {
      return (
        <StatusBadge variant="warning" size="sm">
          Degraded
        </StatusBadge>
      );
    }
    return (
      <StatusBadge variant="error" size="sm">
        Unavailable
      </StatusBadge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title={`Welcome, ${user?.full_name?.split(' ')[0] || 'Admin'}`}
        description="Monitor system readiness, manage station security accounts, and oversee security policies."
        badge={getSystemStatusBadge()}
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Activity className="w-3.5 h-3.5" />}
              onClick={() => navigate('/admin/health')}
            >
              Diagnostics
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<UserPlus className="w-3.5 h-3.5" />}
              onClick={() => navigate('/admin/accounts')}
            >
              Manage Accounts
            </Button>
          </div>
        }
      />

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Accounts"
          value={accountsLoading ? '—' : totalAccounts}
          icon={<Users className="w-4 h-4" />}
          accentColor="violet"
          subtitle="Provisioned users in system"
        />
        <MetricCard
          title="Active Personnel"
          value={accountsLoading ? '—' : activeCount}
          icon={<UserCheck className="w-4 h-4" />}
          accentColor="emerald"
          subtitle="Cleared for terminal access"
        />
        <MetricCard
          title="Inactive Accounts"
          value={accountsLoading ? '—' : inactiveCount}
          icon={<UserX className="w-4 h-4" />}
          accentColor="amber"
          subtitle="Access suspended or pending"
        />
        <MetricCard
          title="System Readiness"
          value={
            healthLoading
              ? 'Checking...'
              : isHealthy
              ? 'Ready'
              : health?.database
              ? 'Degraded'
              : 'Offline'
          }
          icon={<Activity className="w-4 h-4" />}
          accentColor={isHealthy ? 'emerald' : health?.database ? 'amber' : 'rose'}
          badge={getSystemStatusBadge()}
          subtitle="FastAPI + PostgreSQL + pgvector"
        />
      </div>

      {/* Phase 4: Security Operations & Audit Center Shortcuts */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div
          onClick={() => navigate('/security/alerts')}
          className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-amber-500/40 transition-all cursor-pointer group hover:bg-slate-800/30"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 group-hover:scale-110 transition-transform">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-colors" />
          </div>
          <p className="text-xs font-semibold text-slate-200">Alert Center</p>
          <p className="text-[11px] text-slate-400 mt-0.5">Triage active incidents</p>
        </div>

        <div
          onClick={() => navigate('/admin/reports/access')}
          className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-[#7565F5]/40 transition-all cursor-pointer group hover:bg-slate-800/30"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="w-8 h-8 rounded-lg bg-[#7565F5]/10 border border-[#7565F5]/20 flex items-center justify-center text-[#9B8DFC] group-hover:scale-110 transition-transform">
              <FileText className="w-4 h-4" />
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-[#9B8DFC] transition-colors" />
          </div>
          <p className="text-xs font-semibold text-slate-200">Access Reports</p>
          <p className="text-[11px] text-slate-400 mt-0.5">Audit log & CSV export</p>
        </div>

        <div
          onClick={() => navigate('/admin/reports/daily-summary')}
          className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-emerald-500/40 transition-all cursor-pointer group hover:bg-slate-800/30"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 group-hover:scale-110 transition-transform">
              <Calendar className="w-4 h-4" />
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
          </div>
          <p className="text-xs font-semibold text-slate-200">Daily Summary</p>
          <p className="text-[11px] text-slate-400 mt-0.5">24h briefing & dispatch</p>
        </div>

        <div
          onClick={() => navigate('/admin/security-contacts')}
          className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-sky-500/40 transition-all cursor-pointer group hover:bg-slate-800/30"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 group-hover:scale-110 transition-transform">
              <Mail className="w-4 h-4" />
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-sky-400 transition-colors" />
          </div>
          <p className="text-xs font-semibold text-slate-200">Security Contacts</p>
          <p className="text-[11px] text-slate-400 mt-0.5">Email stakeholders & rules</p>
        </div>
      </div>

      {/* Main 2-Column Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Accounts Overview */}
        <div className="lg:col-span-7">
          <Card className="h-full flex flex-col">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Personnel Accounts</CardTitle>
                <p className="text-xs text-slate-400 mt-0.5">
                  Recent authorized users and station assignment status
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
                onClick={() => navigate('/admin/accounts')}
              >
                View All
              </Button>
            </CardHeader>

            <CardContent className="p-0 flex-1">
              {accountsLoading ? (
                <div className="p-6 text-center text-xs text-slate-400">
                  Loading account records...
                </div>
              ) : accounts.length === 0 ? (
                <div className="p-8 text-center">
                  <p className="text-xs text-slate-400 mb-3">No account records found.</p>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate('/admin/accounts')}
                  >
                    Create Account
                  </Button>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {accounts.slice(0, 5).map((acc) => (
                      <TableRow key={acc.id}>
                        <TableCell>
                          <div className="flex items-center gap-2.5">
                            <UserAvatar name={acc.full_name} role={acc.role} size="sm" />
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-slate-100 truncate">
                                {acc.full_name}
                              </p>
                              <p className="text-[11px] text-slate-400 truncate">
                                @{acc.username}
                              </p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            variant={acc.role === 'ADMIN' ? 'primary' : 'info'}
                            size="sm"
                          >
                            {acc.role}
                          </StatusBadge>
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            variant={acc.status === 'active' ? 'success' : 'neutral'}
                            size="sm"
                          >
                            {acc.status}
                          </StatusBadge>
                        </TableCell>
                        <TableCell className="text-right text-xs text-slate-400 font-mono">
                          {new Date(acc.created_at).toLocaleDateString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Real-time System Diagnostics */}
        <div className="lg:col-span-5">
          <Card className="h-full flex flex-col">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Infrastructure Health</CardTitle>
                <p className="text-xs text-slate-400 mt-0.5">
                  Live connection status of foundational core services
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
                onClick={() => navigate('/admin/health')}
              >
                Full Report
              </Button>
            </CardHeader>

            <CardContent className="space-y-3 p-4 sm:p-5 flex-1 flex flex-col justify-between">
              <div className="space-y-3">
                {/* FastAPI Backend */}
                <div className="p-3 rounded-lg bg-[#0E1524] border border-white/[0.04] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#7565F5]/10 border border-[#7565F5]/20 flex items-center justify-center text-[#9B8DFC]">
                      <Server className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-200">FastAPI API Engine</p>
                      <p className="text-[11px] text-slate-400">Core REST endpoints & JWT auth</p>
                    </div>
                  </div>
                  <StatusBadge variant="success" size="sm">
                    Operational
                  </StatusBadge>
                </div>

                {/* PostgreSQL Database */}
                <div className="p-3 rounded-lg bg-[#0E1524] border border-white/[0.04] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
                      <Database className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-200">Supabase PostgreSQL</p>
                      <p className="text-[11px] text-slate-400">Primary relational user datastore</p>
                    </div>
                  </div>
                  {healthLoading ? (
                    <StatusBadge variant="neutral" size="sm">
                      Checking...
                    </StatusBadge>
                  ) : health?.database ? (
                    <StatusBadge variant="success" size="sm">
                      Connected
                    </StatusBadge>
                  ) : (
                    <StatusBadge variant="error" size="sm">
                      Offline
                    </StatusBadge>
                  )}
                </div>

                {/* pgvector Vector Extension */}
                <div className="p-3 rounded-lg bg-[#0E1524] border border-white/[0.04] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                      <Cpu className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-200">pgvector Extension</p>
                      <p className="text-[11px] text-slate-400">Phase 2 biometric index engine</p>
                    </div>
                  </div>
                  {healthLoading ? (
                    <StatusBadge variant="neutral" size="sm">
                      Checking...
                    </StatusBadge>
                  ) : health?.pgvector ? (
                    <StatusBadge variant="success" size="sm">
                      Active
                    </StatusBadge>
                  ) : (
                    <StatusBadge variant="warning" size="sm">
                      Missing
                    </StatusBadge>
                  )}
                </div>
              </div>

              {/* Status Note */}
              <div className="pt-3 border-t border-white/[0.04] flex items-center justify-between text-[11px] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  RBAC Policy Enforcement: Active
                </span>
                <span className="font-mono">Port 8000</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default AdminDashboard;
