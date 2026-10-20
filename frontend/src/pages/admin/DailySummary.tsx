// SmartGuard AI — Phase 4 Daily Security Summary Briefing
// Real-time security metrics, incident breakdown, and on-demand email dispatch.

import { useState, useEffect, useCallback } from 'react';
import {
  Calendar,
  Mail,
  Send,
  RefreshCw,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  ArrowDownCircle,
  ArrowUpCircle,
  Layers,
  Activity,
  TrendingDown,
  Info,
  Loader2,
} from 'lucide-react';
import { reportsApi, type DailySummaryResponse } from '../../api/reports';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';

export default function DailySummary() {
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [summary, setSummary] = useState<DailySummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Email dispatch modal
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [forceSend, setForceSend] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailResult, setEmailResult] = useState<{
    sent_count: number;
    skipped_count: number;
    failed_count: number;
    message?: string;
  } | null>(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const data = await reportsApi.getDailySummary(selectedDate);
      setSummary(data);
    } catch (err: any) {
      console.error('Failed to load daily summary:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const handleSendEmail = async () => {
    setSendingEmail(true);
    setEmailResult(null);
    try {
      const res = await reportsApi.sendDailySummary(selectedDate, forceSend);
      setEmailResult(res);
    } catch (err: any) {
      setEmailResult({
        sent_count: 0,
        skipped_count: 0,
        failed_count: 1,
        message: err.response?.data?.detail || err.message,
      });
    } finally {
      setSendingEmail(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Daily Security Summary"
        description="Consolidated 24-hour campus security report, operational metrics, and automated stakeholder briefing"
        action={
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="bg-transparent text-xs text-slate-200 focus:outline-none"
              />
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setEmailResult(null);
                setShowEmailModal(true);
              }}
            >
              <Mail className="w-4 h-4 mr-1.5" />
              Email Briefing
            </Button>
            <Button variant="secondary" size="sm" onClick={loadSummary} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {loading ? (
        <div className="py-24 flex justify-center items-center">
          <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin" />
        </div>
      ) : !summary ? (
        <Card className="bg-slate-900/60 border-slate-800">
          <CardContent className="py-16 text-center text-slate-400">
            <Info className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p>Could not compute daily security summary for {selectedDate}.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Top Activity Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="bg-slate-900/60 border-slate-800">
              <CardContent className="p-4">
                <p className="text-xs font-medium text-slate-400">Total Attempts</p>
                <p className="text-3xl font-bold text-slate-100 mt-1">{summary.total}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                  <span className="flex items-center gap-1">
                    <ArrowDownCircle className="w-3.5 h-3.5 text-emerald-400" /> {summary.entry} entry
                  </span>
                  <span className="flex items-center gap-1">
                    <ArrowUpCircle className="w-3.5 h-3.5 text-sky-400" /> {summary.exit} exit
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-slate-900/60 border-emerald-500/20">
              <CardContent className="p-4">
                <p className="text-xs font-medium text-slate-400">Access Granted (ALLOW)</p>
                <p className="text-3xl font-bold text-emerald-400 mt-1">{summary.allowed}</p>
                <p className="text-xs text-slate-500 mt-2">
                  {summary.total > 0 ? `${((summary.allowed / summary.total) * 100).toFixed(1)}% of total traffic` : '0%'}
                </p>
              </CardContent>
            </Card>

            <Card className="bg-slate-900/60 border-rose-500/20">
              <CardContent className="p-4">
                <p className="text-xs font-medium text-slate-400">Access Denied (DENY)</p>
                <p className="text-3xl font-bold text-rose-400 mt-1">{summary.denied}</p>
                <p className="text-xs text-slate-500 mt-2">
                  {summary.total > 0 ? `${((summary.denied / summary.total) * 100).toFixed(1)}% violation rate` : '0%'}
                </p>
              </CardContent>
            </Card>

            <Card className="bg-slate-900/60 border-amber-500/20">
              <CardContent className="p-4">
                <p className="text-xs font-medium text-slate-400">Manual Reviews</p>
                <p className="text-3xl font-bold text-amber-400 mt-1">{summary.manual_review}</p>
                <p className="text-xs text-slate-500 mt-2">
                  {summary.pending_reviews} pending officer review
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Security Incidents & Threat Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="bg-slate-900/60 border-slate-800">
              <CardHeader className="border-b border-slate-800/80 pb-3">
                <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  Security Incidents & Violations
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5 space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-rose-500/10 text-rose-400">
                      <AlertTriangle className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">Watchlist Detections</p>
                      <p className="text-xs text-slate-500">Blacklisted or flagged vehicles detected</p>
                    </div>
                  </div>
                  <span className="text-xl font-bold text-rose-400">{summary.watchlist_incidents}</span>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-amber-500/10 text-amber-400">
                      <TrendingDown className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">Repeated Denials</p>
                      <p className="text-xs text-slate-500">3+ denial attempts within 10 minutes</p>
                    </div>
                  </div>
                  <span className="text-xl font-bold text-amber-400">{summary.repeated_denials}</span>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-[#7565F5]/10 text-[#9B8DFC]">
                      <Activity className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">New Alerts Generated</p>
                      <p className="text-xs text-slate-500">Total automated security alerts raised today</p>
                    </div>
                  </div>
                  <span className="text-xl font-bold text-[#9B8DFC]">{summary.new_alerts}</span>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-slate-800 text-slate-300">
                      <Layers className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">Total Unresolved Alerts</p>
                      <p className="text-xs text-slate-500">Across all historical dates</p>
                    </div>
                  </div>
                  <span className="text-xl font-bold text-slate-300">{summary.unresolved_alerts}</span>
                </div>
              </CardContent>
            </Card>

            {/* Top Denial Reasons */}
            <Card className="bg-slate-900/60 border-slate-800">
              <CardHeader className="border-b border-slate-800/80 pb-3">
                <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-rose-400" />
                  Top Gate Denial Reasons ({summary.date})
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5">
                {summary.top_denial_reasons.length === 0 ? (
                  <div className="py-12 text-center text-slate-500 text-xs">
                    No denial events recorded on this date.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {summary.top_denial_reasons.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-800 text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center font-bold text-[10px]">
                            {idx + 1}
                          </span>
                          <span className="font-mono font-medium text-slate-200">{item.code}</span>
                        </div>
                        <span className="px-2.5 py-1 rounded-md bg-rose-500/10 text-rose-400 font-bold border border-rose-500/20">
                          {item.count} occurrences
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Email Send Modal */}
      {showEmailModal && (
        <Modal
          isOpen={showEmailModal}
          onClose={() => setShowEmailModal(false)}
          title="Send Daily Summary Briefing"
          maxWidth="md"
        >
          <div className="space-y-4 text-xs text-slate-300">
            <p>
              Dispatch an executive email briefing with the security summary for{' '}
              <strong className="text-white">{selectedDate}</strong> to all active security contacts with daily summaries enabled.
            </p>

            <label className="flex items-center gap-2 p-3 bg-slate-800/60 rounded-lg border border-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={forceSend}
                onChange={(e) => setForceSend(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-[#7565F5]"
              />
              <span>
                <strong>Force send:</strong> Bypass duplicate prevention (e.g. re-send if previously delivered today).
              </span>
            </label>

            {emailResult && (
              <div
                className={`p-3 rounded-lg border ${
                  emailResult.failed_count === 0
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                }`}
              >
                <p className="font-semibold">
                  {emailResult.failed_count === 0 ? '✓ Briefing Dispatched' : 'Notice'}
                </p>
                <p className="mt-1">
                  Sent: {emailResult.sent_count} | Skipped: {emailResult.skipped_count} | Failed: {emailResult.failed_count}
                </p>
                {emailResult.message && <p className="mt-1 text-[11px] opacity-80">{emailResult.message}</p>}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
              <Button variant="ghost" size="sm" onClick={() => setShowEmailModal(false)}>
                Close
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSendEmail}
                disabled={sendingEmail}
              >
                <Send className={`w-3.5 h-3.5 mr-1.5 ${sendingEmail ? 'animate-pulse' : ''}`} />
                {sendingEmail ? 'Dispatching...' : 'Send Briefing Now'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
