// SmartGuard AI — Phase 4 Security Alert Center
// Comprehensive Incident Lifecycle Management: Acknowledge, Investigate, Note, Resolve, and Dismiss.

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  Eye,
  RefreshCw,
  Search,
  XCircle,
  Send,
  Activity,
  X,
  Loader2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  alertsApi,
  type AlertSummary,
  type AlertDetail,
  type AlertMetrics,
  type AlertSeverity,
  type AlertStatus,
} from '../../api/alerts';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge, type BadgeVariant } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';

const SEVERITY_COLORS: Record<AlertSeverity, { bg: string; text: string; border: string; badge: BadgeVariant }> = {
  CRITICAL: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30', badge: 'error' },
  HIGH: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', badge: 'warning' },
  MEDIUM: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30', badge: 'warning' },
  LOW: { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/30', badge: 'info' },
};

const STATUS_BADGES: Record<AlertStatus, BadgeVariant> = {
  OPEN: 'error',
  ACKNOWLEDGED: 'warning',
  INVESTIGATING: 'primary',
  RESOLVED: 'success',
  DISMISSED: 'neutral',
};

export default function AlertCenter() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  // Data states
  const [metrics, setMetrics] = useState<AlertMetrics | null>(null);
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('UNRESOLVED');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [searchPlate, setSearchPlate] = useState<string>('');
  const [page, setPage] = useState(1);
  const limit = 20;

  // Selected Alert Detail Modal
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Note form
  const [newNote, setNewNote] = useState('');
  const [submittingNote, setSubmittingNote] = useState(false);

  // Resolution / Dismissal Prompt Modal
  const [actionType, setActionType] = useState<'RESOLVE' | 'DISMISS' | null>(null);
  const [actionReason, setActionReason] = useState('');
  const [submittingAction, setSubmittingAction] = useState(false);

  // Load metrics
  const loadMetrics = useCallback(async () => {
    try {
      const data = await alertsApi.getMetrics();
      setMetrics(data);
    } catch (err: any) {
      console.error('Failed to load alert metrics:', err);
    }
  }, []);

  // Load alert list
  const loadAlerts = useCallback(async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    else setRefreshing(true);

    try {
      const skip = (page - 1) * limit;
      const effectiveStatus = statusFilter === 'UNRESOLVED' ? undefined : statusFilter || undefined;

      const res = await alertsApi.listAlerts({
        status: effectiveStatus,
        severity: severityFilter || undefined,
        category: categoryFilter || undefined,
        plate: searchPlate.trim() || undefined,
        skip,
        limit,
      });

      let items = res.items;
      if (statusFilter === 'UNRESOLVED') {
        items = items.filter(a => a.status !== 'RESOLVED' && a.status !== 'DISMISSED');
      }

      setAlerts(items);
      setTotal(res.total);
    } catch (err: any) {
      console.error('Failed to load security alerts:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, statusFilter, severityFilter, categoryFilter, searchPlate]);

  // Initial load
  useEffect(() => {
    loadMetrics();
    loadAlerts();
  }, [loadMetrics, loadAlerts]);

  // Auto-refresh timer
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadMetrics();
      loadAlerts(true);
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadMetrics, loadAlerts]);

  // Open detail modal
  const openDetail = async (id: string) => {
    setSelectedAlertId(id);
    setDetailLoading(true);
    try {
      const data = await alertsApi.getAlert(id);
      setDetail(data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to fetch alert details');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedAlertId(null);
    setDetail(null);
    setNewNote('');
    setActionType(null);
  };

  // Actions
  const handleAcknowledge = async () => {
    if (!selectedAlertId) return;
    try {
      const updated = await alertsApi.acknowledgeAlert(selectedAlertId, 'Acknowledged by operator');
      setDetail(updated);
      loadMetrics();
      loadAlerts(true);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to acknowledge alert');
    }
  };

  const handleInvestigate = async () => {
    if (!selectedAlertId) return;
    try {
      const updated = await alertsApi.investigateAlert(selectedAlertId, 'Investigation commenced');
      setDetail(updated);
      loadMetrics();
      loadAlerts(true);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update alert state');
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAlertId || !newNote.trim()) return;
    setSubmittingNote(true);
    try {
      const updated = await alertsApi.addNote(selectedAlertId, newNote.trim());
      setDetail(updated);
      setNewNote('');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to add note');
    } finally {
      setSubmittingNote(false);
    }
  };

  const handleExecuteAction = async () => {
    if (!selectedAlertId || !actionType) return;
    if (!actionReason.trim()) {
      alert('A reason is required to resolve or dismiss an alert.');
      return;
    }
    setSubmittingAction(true);
    try {
      let updated: AlertDetail;
      if (actionType === 'RESOLVE') {
        updated = await alertsApi.resolveAlert(selectedAlertId, actionReason.trim());
      } else {
        updated = await alertsApi.dismissAlert(selectedAlertId, actionReason.trim());
      }
      setDetail(updated);
      setActionType(null);
      setActionReason('');
      loadMetrics();
      loadAlerts(true);
    } catch (err: any) {
      alert(err.response?.data?.detail || `Failed to ${actionType.toLowerCase()} alert`);
    } finally {
      setSubmittingAction(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Security Alert Center"
        description="Real-time incident response, lifecycle tracking, and investigative auditing"
        action={
          <div className="flex items-center gap-3">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                autoRefresh
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              <Activity className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-pulse text-emerald-400' : ''}`} />
              {autoRefresh ? 'Live updates: 10s' : 'Auto-refresh off'}
            </button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                loadMetrics();
                loadAlerts();
              }}
              disabled={refreshing || loading}
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* Metrics Row */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <Card className="bg-slate-900/60 border-rose-500/20 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Critical / High</p>
              <p className="text-2xl font-bold text-rose-400 mt-1">{metrics.critical_high_unresolved}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Requires priority</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-amber-500/20 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Open Incidents</p>
              <p className="text-2xl font-bold text-amber-400 mt-1">{metrics.open}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Awaiting triage</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-sky-500/20 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Acknowledged</p>
              <p className="text-2xl font-bold text-sky-400 mt-1">{metrics.acknowledged}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Officer notified</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-[#7565F5]/20 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Investigating</p>
              <p className="text-2xl font-bold text-[#9B8DFC] mt-1">{metrics.investigating}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Under active review</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-emerald-500/20 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Resolved</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">{metrics.resolved}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Closed with reason</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-sm">
            <CardContent className="p-4">
              <p className="text-xs font-medium text-slate-400">Dismissed</p>
              <p className="text-2xl font-bold text-slate-400 mt-1">{metrics.dismissed}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">Admin dismissed</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filter and Search Bar */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search Plate */}
            <div className="relative min-w-[200px] flex-1">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search plate number..."
                value={searchPlate}
                onChange={(e) => {
                  setSearchPlate(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-9 pr-3 py-1.5 text-sm bg-slate-800/80 border border-slate-700/80 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1 bg-slate-800/80 p-1 rounded-lg border border-slate-700/80 text-xs">
              {[
                { id: 'UNRESOLVED', label: 'Unresolved' },
                { id: 'OPEN', label: 'Open' },
                { id: 'INVESTIGATING', label: 'Investigating' },
                { id: 'RESOLVED', label: 'Resolved' },
                { id: '', label: 'All' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => {
                    setStatusFilter(tab.id);
                    setPage(1);
                  }}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    statusFilter === tab.id
                      ? 'bg-[#7565F5] text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Severity Filter */}
            <select
              value={severityFilter}
              onChange={(e) => {
                setSeverityFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-1.5 text-xs bg-slate-800/80 border border-slate-700/80 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
            >
              <option value="">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            {/* Category Filter */}
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-1.5 text-xs bg-slate-800/80 border border-slate-700/80 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
            >
              <option value="">All Categories</option>
              <option value="WATCHLIST_HIT">Watchlist Hit</option>
              <option value="REPEATED_DENIAL">Repeated Denial</option>
              <option value="DENIED_ACCESS">Denied Access</option>
              <option value="MANUAL_REVIEW">Manual Review</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Alerts Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-20 flex justify-center items-center">
              <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin" />
            </div>
          ) : alerts.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <ShieldAlert className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium">No alerts match the selected criteria</p>
              <p className="text-xs text-slate-500 mt-1">Change your filters or search terms to inspect more events.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-950/40">
                    <th className="py-3.5 px-4">Severity</th>
                    <th className="py-3.5 px-4">Category</th>
                    <th className="py-3.5 px-4">Title / Description</th>
                    <th className="py-3.5 px-4">Plate</th>
                    <th className="py-3.5 px-4">Occurrences</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Detected At</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {alerts.map((alert) => {
                    const sev = SEVERITY_COLORS[alert.severity] || SEVERITY_COLORS.LOW;
                    return (
                      <tr
                        key={alert.id}
                        className="hover:bg-slate-800/30 transition-colors cursor-pointer group"
                        onClick={() => openDetail(alert.id)}
                      >
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <StatusBadge variant={sev.badge} size="sm">
                            {alert.severity}
                          </StatusBadge>
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-xs font-medium text-slate-300">
                          {alert.category.replace('_', ' ')}
                        </td>
                        <td className="py-3.5 px-4 max-w-md">
                          <p className="font-medium text-slate-200 truncate group-hover:text-[#9B8DFC] transition-colors">
                            {alert.title}
                          </p>
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {alert.detected_plate ? (
                            <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                              {alert.detected_plate}
                            </span>
                          ) : (
                            <span className="text-slate-500 text-xs">—</span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-xs text-slate-400">
                          {alert.occurrence_count > 1 ? (
                            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-amber-300 font-semibold text-[11px]">
                              {alert.occurrence_count}×
                            </span>
                          ) : (
                            '1'
                          )}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <StatusBadge variant={STATUS_BADGES[alert.status]} size="sm">
                            {alert.status}
                          </StatusBadge>
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-xs text-slate-400">
                          {new Date(alert.first_detected_at).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              openDetail(alert.id);
                            }}
                          >
                            <Eye className="w-4 h-4 text-slate-400 group-hover:text-white" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > limit && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs text-slate-400">
              <p>
                Showing {(page - 1) * limit + 1} to {Math.min(page * limit, total)} of {total} alerts
              </p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page * limit >= total}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Alert Detail Modal */}
      {selectedAlertId && (
        <Modal
          isOpen={!!selectedAlertId}
          onClose={closeDetail}
          title={detail ? `[${detail.severity}] ${detail.title}` : 'Incident Details'}
          maxWidth="xl"
        >
          {detailLoading || !detail ? (
            <div className="py-16 flex justify-center">
              <Loader2 className="w-7 h-7 text-[#7565F5] animate-spin" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Meta information grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/40 p-4 rounded-xl border border-slate-800/80 text-xs">
                <div>
                  <span className="text-slate-500">Status</span>
                  <div className="mt-1">
                    <StatusBadge variant={STATUS_BADGES[detail.status]} size="sm">
                      {detail.status}
                    </StatusBadge>
                  </div>
                </div>
                <div>
                  <span className="text-slate-500">Category</span>
                  <p className="mt-1 font-medium text-slate-200">{detail.category}</p>
                </div>
                <div>
                  <span className="text-slate-500">Detected Plate</span>
                  <p className="mt-1 font-mono font-medium text-slate-200">
                    {detail.detected_plate || 'None'}
                  </p>
                </div>
                <div>
                  <span className="text-slate-500">Occurrences</span>
                  <p className="mt-1 font-medium text-slate-200">{detail.occurrence_count}</p>
                </div>
                <div>
                  <span className="text-slate-500">First Detected</span>
                  <p className="mt-1 text-slate-300">{new Date(detail.first_detected_at).toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-slate-500">Last Updated</span>
                  <p className="mt-1 text-slate-300">{new Date(detail.last_updated_at).toLocaleString()}</p>
                </div>
                {detail.resolution_reason && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Resolution Reason</span>
                    <p className="mt-1 text-emerald-300 font-medium">{detail.resolution_reason}</p>
                  </div>
                )}
              </div>

              {/* Description */}
              {detail.description && (
                <div className="bg-slate-800/40 p-3.5 rounded-lg border border-slate-700/50">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                    Event Description / Policy Details
                  </span>
                  <p className="text-sm text-slate-200 whitespace-pre-wrap">{detail.description}</p>
                </div>
              )}

              {/* Lifecycle Action Bar */}
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800">
                {detail.status === 'OPEN' && (
                  <Button variant="secondary" size="sm" onClick={handleAcknowledge}>
                    <CheckCircle className="w-4 h-4 mr-1.5 text-sky-400" />
                    Acknowledge
                  </Button>
                )}

                {(detail.status === 'OPEN' || detail.status === 'ACKNOWLEDGED') && (
                  <Button variant="secondary" size="sm" onClick={handleInvestigate}>
                    <Eye className="w-4 h-4 mr-1.5 text-[#9B8DFC]" />
                    Start Investigation
                  </Button>
                )}

                {detail.status !== 'RESOLVED' && detail.status !== 'DISMISSED' && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setActionType('RESOLVE');
                      setActionReason('');
                    }}
                  >
                    <CheckCircle className="w-4 h-4 mr-1.5" />
                    Resolve Alert
                  </Button>
                )}

                {isAdmin && detail.status !== 'DISMISSED' && detail.status !== 'RESOLVED' && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      setActionType('DISMISS');
                      setActionReason('');
                    }}
                  >
                    <XCircle className="w-4 h-4 mr-1.5" />
                    Dismiss (Admin)
                  </Button>
                )}
              </div>

              {/* Action Prompt (Resolve / Dismiss Reason) */}
              {actionType && (
                <div className="bg-slate-900 border border-slate-700 p-4 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-200">
                      {actionType === 'RESOLVE' ? 'Resolve Security Alert' : 'Dismiss Alert as False Positive'}
                    </span>
                    <button onClick={() => setActionType(null)} className="text-slate-400 hover:text-white">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Enter resolution notes / justification (required)..."
                    value={actionReason}
                    onChange={(e) => setActionReason(e.target.value)}
                    className="w-full px-3 py-2 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
                    autoFocus
                  />
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setActionType(null)}>
                      Cancel
                    </Button>
                    <Button
                      variant={actionType === 'RESOLVE' ? 'primary' : 'danger'}
                      size="sm"
                      onClick={handleExecuteAction}
                      disabled={submittingAction || !actionReason.trim()}
                    >
                      Confirm {actionType === 'RESOLVE' ? 'Resolution' : 'Dismissal'}
                    </Button>
                  </div>
                </div>
              )}

              {/* Notes & Timeline */}
              <div className="space-y-3">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                  Investigation Log & Audit History ({detail.notes.length})
                </span>

                <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
                  {detail.notes.length === 0 ? (
                    <p className="text-xs text-slate-500 py-2">No notes recorded yet.</p>
                  ) : (
                    detail.notes.map((note) => (
                      <div
                        key={note.id}
                        className={`p-3 rounded-lg text-xs border ${
                          note.note_type === 'STATUS_CHANGE'
                            ? 'bg-slate-900/60 border-slate-800 text-slate-400'
                            : 'bg-slate-800/50 border-slate-700/60 text-slate-200'
                        }`}
                      >
                        <div className="flex justify-between items-center mb-1 text-[11px] text-slate-500">
                          <span className="font-semibold text-slate-400">{note.note_type}</span>
                          <span>{new Date(note.created_at).toLocaleString()}</span>
                        </div>
                        <p className="whitespace-pre-wrap">{note.body}</p>
                      </div>
                    ))
                  )}
                </div>

                {/* Add Note Input */}
                <form onSubmit={handleAddNote} className="flex gap-2 pt-2">
                  <input
                    type="text"
                    placeholder="Add an investigation note or update..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    className="flex-1 px-3 py-2 text-xs bg-slate-800/80 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
                  />
                  <Button variant="secondary" size="sm" type="submit" disabled={submittingNote || !newNote.trim()}>
                    <Send className="w-3.5 h-3.5 mr-1" />
                    Post
                  </Button>
                </form>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
