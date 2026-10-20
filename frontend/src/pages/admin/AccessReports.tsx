// SmartGuard AI — Phase 4 Access Reports & Audit Logging
// Filterable, searchable access logs with server-side pagination and safe CSV export.

import { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  Download,
  Search,
  ArrowDownCircle,
  ArrowUpCircle,
  RefreshCw,
  Eye,
  Loader2,
} from 'lucide-react';
import {
  reportsApi,
  type AccessReportRow,
  type AccessReportFilterParams,
} from '../../api/reports';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge, type BadgeVariant } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';

export default function AccessReports() {
  const [items, setItems] = useState<AccessReportRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  // Filters
  const [direction, setDirection] = useState<string>('');
  const [decision, setDecision] = useState<string>('');
  const [plate, setPlate] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [watchlistOnly, setWatchlistOnly] = useState<boolean>(false);
  const [reviewPending, setReviewPending] = useState<boolean>(false);
  const [page, setPage] = useState(1);
  const limit = 25;

  // Detail Modal
  const [selectedRow, setSelectedRow] = useState<AccessReportRow | null>(null);

  const getFilterParams = useCallback((): AccessReportFilterParams => {
    return {
      direction: direction || undefined,
      decision: decision || undefined,
      plate: plate.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      watchlist_only: watchlistOnly || undefined,
      review_pending: reviewPending || undefined,
      skip: (page - 1) * limit,
      limit,
    };
  }, [direction, decision, plate, dateFrom, dateTo, watchlistOnly, reviewPending, page]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await reportsApi.listAccessReport(getFilterParams());
      setItems(res.items);
      setTotal(res.total);
    } catch (err: any) {
      console.error('Failed to load access report:', err);
    } finally {
      setLoading(false);
    }
  }, [getFilterParams]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Export CSV
  const handleExportCsv = async () => {
    setExporting(true);
    try {
      const blob = await reportsApi.downloadCsv(getFilterParams());
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const today = new Date().toISOString().slice(0, 10);
      a.download = `smartguard_access_report_${today}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('Failed to export CSV: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExporting(false);
    }
  };

  const getDecisionBadge = (dec: string): BadgeVariant => {
    switch (dec) {
      case 'ALLOW':
        return 'success';
      case 'DENY':
        return 'error';
      case 'MANUAL_REVIEW':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Gate Access Audit & Reports"
        description="Comprehensive historical verification log, policy evaluation audit, and compliance reports"
        action={
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExportCsv}
              disabled={exporting || loading}
            >
              <Download className={`w-4 h-4 mr-1.5 ${exporting ? 'animate-bounce' : ''}`} />
              {exporting ? 'Exporting CSV...' : 'Export CSV'}
            </Button>
            <Button variant="secondary" size="sm" onClick={loadData} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* Filter Toolbar */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardContent className="p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {/* Search Plate */}
            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Search Plate</label>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Plate number..."
                  value={plate}
                  onChange={(e) => {
                    setPlate(e.target.value);
                    setPage(1);
                  }}
                  className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
                />
              </div>
            </div>

            {/* Decision Filter */}
            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Access Decision</label>
              <select
                value={decision}
                onChange={(e) => {
                  setDecision(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              >
                <option value="">All Decisions</option>
                <option value="ALLOW">ALLOW</option>
                <option value="DENY">DENY</option>
                <option value="MANUAL_REVIEW">MANUAL_REVIEW</option>
              </select>
            </div>

            {/* Direction Filter */}
            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Direction</label>
              <select
                value={direction}
                onChange={(e) => {
                  setDirection(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              >
                <option value="">All Directions</option>
                <option value="ENTRY">ENTRY</option>
                <option value="EXIT">EXIT</option>
              </select>
            </div>

            {/* Date From */}
            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">From Date</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            {/* Date To */}
            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">To Date</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            {/* Special Toggles */}
            <div className="flex flex-col justify-end gap-1.5">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={watchlistOnly}
                  onChange={(e) => {
                    setWatchlistOnly(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded border-slate-700 bg-slate-800 text-[#7565F5] focus:ring-0"
                />
                Watchlist hits only
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={reviewPending}
                  onChange={(e) => {
                    setReviewPending(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded border-slate-700 bg-slate-800 text-[#7565F5] focus:ring-0"
                />
                Pending reviews only
              </label>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reports Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-20 flex justify-center items-center">
              <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <FileText className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium">No access attempts match your query</p>
              <p className="text-xs text-slate-500 mt-1">Try broadening your date range or clearing filter options.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-950/40">
                    <th className="py-3.5 px-4">Timestamp</th>
                    <th className="py-3.5 px-4">Direction</th>
                    <th className="py-3.5 px-4">Decision</th>
                    <th className="py-3.5 px-4">Gate</th>
                    <th className="py-3.5 px-4">Detected Plate</th>
                    <th className="py-3.5 px-4">Reasons / Notes</th>
                    <th className="py-3.5 px-4">Watchlist</th>
                    <th className="py-3.5 px-4">Latency</th>
                    <th className="py-3.5 px-4 text-right">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {items.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedRow(row)}
                      className="hover:bg-slate-800/30 transition-colors cursor-pointer group"
                    >
                      <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-300">
                        {new Date(row.timestamp).toLocaleString([], {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className="flex items-center gap-1.5 text-xs font-medium text-slate-300">
                          {row.direction === 'ENTRY' ? (
                            <ArrowDownCircle className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <ArrowUpCircle className="w-3.5 h-3.5 text-sky-400" />
                          )}
                          {row.direction}
                        </span>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <StatusBadge variant={getDecisionBadge(row.decision)} size="sm">
                          {row.decision}
                        </StatusBadge>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-xs font-medium text-slate-300">
                        {row.gate_result}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {row.detected_plate ? (
                          <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
                            {row.detected_plate}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4 max-w-xs">
                        <p className="text-xs text-slate-300 truncate">
                          {row.reason_text || (row.reason_codes && row.reason_codes.join(', ')) || 'All checks passed'}
                        </p>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {row.watchlist_hit ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">
                            {row.watchlist_severity || 'HIT'}
                          </span>
                        ) : (
                          <span className="text-slate-600 text-xs">None</span>
                        )}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-400">
                        {row.processing_ms ? `${row.processing_ms}ms` : '—'}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRow(row);
                          }}
                        >
                          <Eye className="w-4 h-4 text-slate-400 group-hover:text-white" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > limit && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs text-slate-400">
              <p>
                Showing {(page - 1) * limit + 1} to {Math.min(page * limit, total)} of {total} records
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

      {/* Detail Modal */}
      {selectedRow && (
        <Modal
          isOpen={!!selectedRow}
          onClose={() => setSelectedRow(null)}
          title={`Attempt Details — ${selectedRow.direction} (${selectedRow.decision})`}
          maxWidth="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 bg-slate-950/40 p-4 rounded-xl border border-slate-800">
              <div>
                <span className="text-slate-500">Attempt ID</span>
                <p className="mt-1 font-mono text-slate-300 truncate">{selectedRow.id}</p>
              </div>
              <div>
                <span className="text-slate-500">Timestamp</span>
                <p className="mt-1 text-slate-300">{new Date(selectedRow.timestamp).toLocaleString()}</p>
              </div>
              <div>
                <span className="text-slate-500">Gate Execution</span>
                <p className="mt-1 font-semibold text-slate-200">{selectedRow.gate_result}</p>
              </div>
              <div>
                <span className="text-slate-500">Detected Plate</span>
                <p className="mt-1 font-mono text-slate-200">{selectedRow.detected_plate || 'None'}</p>
              </div>
              <div>
                <span className="text-slate-500">Matched Person ID</span>
                <p className="mt-1 font-mono text-slate-300 truncate">{selectedRow.matched_person_id || 'None'}</p>
              </div>
              <div>
                <span className="text-slate-500">Processing Latency</span>
                <p className="mt-1 text-slate-300">{selectedRow.processing_ms} ms</p>
              </div>
            </div>

            {/* Policy evaluation details */}
            <div className="bg-slate-800/40 p-4 rounded-xl border border-slate-700/60 space-y-2">
              <span className="font-semibold text-slate-300 uppercase tracking-wider block">Policy Evaluation Details</span>
              <div className="grid grid-cols-2 gap-2 text-slate-300">
                <p>Ownership Verified: <span className="font-semibold text-slate-100">{String(selectedRow.ownership_ok ?? 'N/A')}</span></p>
                <p>Schedule Permitted: <span className="font-semibold text-slate-100">{String(selectedRow.schedule_ok ?? 'N/A')}</span></p>
                <p>Watchlist Triggered: <span className="font-semibold text-slate-100">{String(selectedRow.watchlist_hit ?? 'False')}</span></p>
                <p>Review Required: <span className="font-semibold text-slate-100">{String(selectedRow.review_required)}</span></p>
              </div>
              {selectedRow.reason_text && (
                <div className="pt-2 border-t border-slate-700/50">
                  <span className="text-slate-400">Detailed Reason:</span>
                  <p className="text-slate-200 font-medium mt-0.5">{selectedRow.reason_text}</p>
                </div>
              )}
            </div>

            {/* Manual Review Outcome */}
            {selectedRow.review_required && (
              <div className="bg-amber-500/10 p-3.5 rounded-xl border border-amber-500/25">
                <span className="font-semibold text-amber-400 block mb-1">Manual Review State</span>
                <p className="text-slate-200">
                  Resolved: {selectedRow.review_resolved ? 'Yes' : 'Pending Action'}
                </p>
                {selectedRow.review_resolution && (
                  <p className="text-slate-200 mt-1">
                    Resolution: <span className="font-semibold">{selectedRow.review_resolution}</span>
                    {selectedRow.review_reason && ` — "${selectedRow.review_reason}"`}
                  </p>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
