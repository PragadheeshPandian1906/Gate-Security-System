// SmartGuard AI — Phase 4 Notification Delivery Logs & Dispatch Audit
// Inspect delivery statuses, track retries, and trigger manual dispatch recovery.

import { useState, useEffect, useCallback } from 'react';
import {
  Mail,
  RefreshCw,
  Search,
  RotateCcw,
  Eye,
  Loader2,
} from 'lucide-react';
import {
  notificationsApi,
  type NotificationLogItem,
  type NotificationFilterParams,
  type NotificationStatus,
} from '../../api/notifications';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge, type BadgeVariant } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';

const STATUS_BADGES: Record<NotificationStatus, BadgeVariant> = {
  SENT: 'success',
  PENDING: 'info',
  SENDING: 'primary',
  RETRY_SCHEDULED: 'warning',
  FAILED: 'error',
};

export default function NotificationHistory() {
  const [items, setItems] = useState<NotificationLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [bulkRetrying, setBulkRetrying] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [searchRecipient, setSearchRecipient] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [page, setPage] = useState(1);
  const limit = 25;

  // Selected item modal for sanitized error inspection
  const [selectedItem, setSelectedItem] = useState<NotificationLogItem | null>(null);

  const getParams = useCallback((): NotificationFilterParams => {
    return {
      status: statusFilter || undefined,
      notification_type: typeFilter || undefined,
      recipient: searchRecipient.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      skip: (page - 1) * limit,
      limit,
    };
  }, [statusFilter, typeFilter, searchRecipient, dateFrom, dateTo, page]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationsApi.listNotifications(getParams());
      setItems(res.items);
      setTotal(res.total);
    } catch (err: any) {
      console.error('Failed to load notification history:', err);
    } finally {
      setLoading(false);
    }
  }, [getParams]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetryOne = async (id: string) => {
    setRetryingId(id);
    try {
      await notificationsApi.retryNotification(id);
      loadData();
    } catch (err: any) {
      alert('Retry failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setRetryingId(null);
    }
  };

  const handleRetryAll = async () => {
    if (!window.confirm('Reschedule all failed notifications for retry?')) return;
    setBulkRetrying(true);
    try {
      const res = await notificationsApi.retryAllFailed();
      alert(`Rescheduled ${res.rescheduled} failed notification(s).`);
      loadData();
    } catch (err: any) {
      alert('Bulk retry failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setBulkRetrying(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notification Delivery History"
        description="Delivery tracking, idempotency logs, Brevo/SMTP status codes, and retry management"
        action={
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRetryAll}
              disabled={bulkRetrying || loading}
            >
              <RotateCcw className={`w-4 h-4 mr-1.5 ${bulkRetrying ? 'animate-spin' : ''}`} />
              Retry All Failed
            </Button>
            <Button variant="secondary" size="sm" onClick={loadData} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* Filter toolbar */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
            <div className="relative">
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Search Recipient</label>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Recipient email..."
                  value={searchRecipient}
                  onChange={(e) => {
                    setSearchRecipient(e.target.value);
                    setPage(1);
                  }}
                  className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
                />
              </div>
            </div>

            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              >
                <option value="">All Statuses</option>
                <option value="SENT">SENT</option>
                <option value="PENDING">PENDING</option>
                <option value="RETRY_SCHEDULED">RETRY_SCHEDULED</option>
                <option value="FAILED">FAILED</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-medium text-slate-400 block mb-1">Type</label>
              <select
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              >
                <option value="">All Types</option>
                <option value="ALERT">ALERT</option>
                <option value="DAILY_SUMMARY">DAILY_SUMMARY</option>
                <option value="TEST">TEST</option>
              </select>
            </div>

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
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-20 flex justify-center items-center">
              <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <Mail className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium">No notification events recorded</p>
              <p className="text-xs text-slate-500 mt-1">Delivery logs will appear as alerts and summaries are dispatched.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-950/40">
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Type</th>
                    <th className="py-3.5 px-4">Recipient</th>
                    <th className="py-3.5 px-4">Subject</th>
                    <th className="py-3.5 px-4">Attempts</th>
                    <th className="py-3.5 px-4">Sent / Attempted</th>
                    <th className="py-3.5 px-4">Provider</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-xs">
                  {items.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedItem(row)}
                      className="hover:bg-slate-800/30 transition-colors cursor-pointer group"
                    >
                      <td className="py-3 px-4 whitespace-nowrap">
                        <StatusBadge variant={STATUS_BADGES[row.status] || 'neutral'} size="sm">
                          {row.status}
                        </StatusBadge>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap font-medium text-slate-300">
                        {row.notification_type}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap font-mono text-slate-200">
                        {row.recipient_email}
                      </td>
                      <td className="py-3 px-4 max-w-xs">
                        <p className="truncate text-slate-300 font-medium">{row.subject}</p>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-slate-400">
                        {row.attempt_count} / {row.max_attempts}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-slate-400">
                        {row.sent_at
                          ? new Date(row.sent_at).toLocaleString([], {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : row.last_attempted_at
                          ? new Date(row.last_attempted_at).toLocaleString([], {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : 'Pending'}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-slate-400">
                        {row.provider || '—'}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {row.status !== 'SENT' && (
                            <Button
                              variant="secondary"
                              size="sm"
                              title="Retry Delivery"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRetryOne(row.id);
                              }}
                              disabled={retryingId === row.id}
                            >
                              <RotateCcw className={`w-3.5 h-3.5 ${retryingId === row.id ? 'animate-spin' : ''}`} />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Inspect Details"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedItem(row);
                            }}
                          >
                            <Eye className="w-3.5 h-3.5 text-slate-400 group-hover:text-white" />
                          </Button>
                        </div>
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
                Showing {(page - 1) * limit + 1} to {Math.min(page * limit, total)} of {total} delivery logs
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

      {/* Error inspection modal */}
      {selectedItem && (
        <Modal
          isOpen={!!selectedItem}
          onClose={() => setSelectedItem(null)}
          title="Notification Delivery Audit"
          maxWidth="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 bg-slate-950/40 p-3.5 rounded-xl border border-slate-800">
              <div>
                <span className="text-slate-500">Log ID</span>
                <p className="mt-1 font-mono text-slate-300 truncate">{selectedItem.id}</p>
              </div>
              <div>
                <span className="text-slate-500">Status</span>
                <div className="mt-1">
                  <StatusBadge variant={STATUS_BADGES[selectedItem.status]} size="sm">
                    {selectedItem.status}
                  </StatusBadge>
                </div>
              </div>
              <div>
                <span className="text-slate-500">Recipient</span>
                <p className="mt-1 font-mono text-slate-200">{selectedItem.recipient_email}</p>
              </div>
              <div>
                <span className="text-slate-500">Type</span>
                <p className="mt-1 font-semibold text-slate-200">{selectedItem.notification_type}</p>
              </div>
              <div>
                <span className="text-slate-500">Created At</span>
                <p className="mt-1 text-slate-300">{new Date(selectedItem.created_at).toLocaleString()}</p>
              </div>
              <div>
                <span className="text-slate-500">Provider Message ID</span>
                <p className="mt-1 font-mono text-slate-300">{selectedItem.provider_message_id || 'None'}</p>
              </div>
            </div>

            <div>
              <span className="text-slate-400 font-medium block mb-1">Subject</span>
              <div className="p-2.5 bg-slate-800/80 rounded-lg text-slate-200 font-medium">
                {selectedItem.subject}
              </div>
            </div>

            {selectedItem.error_detail && (
              <div className="bg-rose-500/10 p-3.5 rounded-xl border border-rose-500/30">
                <span className="font-semibold text-rose-400 block mb-1">Sanitized Provider Error Detail</span>
                <pre className="font-mono text-[11px] text-rose-200 whitespace-pre-wrap">
                  {selectedItem.error_detail}
                </pre>
              </div>
            )}

            {selectedItem.next_retry_at && (
              <div className="bg-amber-500/10 p-3 rounded-lg border border-amber-500/25 text-amber-300">
                Next retry scheduled at: {new Date(selectedItem.next_retry_at).toLocaleString()}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
