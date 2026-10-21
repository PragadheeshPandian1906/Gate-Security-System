import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Clock3,
  LogIn,
  LogOut,
  ShieldAlert,
  UsersRound,
} from 'lucide-react';
import { accessApi, type CampusAnalytics } from '../../api/phase3';
import { Card } from '../ui/Card';

const REFRESH_INTERVAL_MS = 15_000;

function formatCategory(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

export function CampusEntryOverview() {
  const [analytics, setAnalytics] = useState<CampusAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    let requestInFlight = false;

    const refresh = async () => {
      if (requestInFlight) return;
      requestInFlight = true;
      try {
        const response = await accessApi.getCampusAnalytics(controller.signal);
        if (mounted) {
          setAnalytics(response.data);
          setError(null);
          setIsLoading(false);
        }
      } catch (refreshError) {
        if (mounted && !controller.signal.aborted) {
          console.warn('Campus analytics refresh failed', refreshError);
          setError('Campus analytics could not be refreshed.');
          setIsLoading(false);
        }
      } finally {
        requestInFlight = false;
      }
    };

    void refresh();
    const intervalId = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
    return () => {
      mounted = false;
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, []);

  const metrics = [
    { label: 'Total Entries Today', value: 'Not tracked', icon: LogIn, color: 'text-emerald-300' },
    { label: 'Currently Inside Campus', value: 'Not tracked', icon: UsersRound, color: 'text-cyan-300' },
    { label: 'Total Exits Today', value: 'Not tracked', icon: LogOut, color: 'text-violet-300' },
    {
      label: 'Denied Access Today',
      value: analytics ? analytics.denied_access_today.toLocaleString() : isLoading ? '…' : '—',
      icon: ShieldAlert,
      color: 'text-rose-300',
    },
  ];

  const maxAuthorizationCount = Math.max(
    1,
    ...(analytics?.hourly_activity.map(
      (hour) => hour.entry_authorizations + hour.exit_authorizations
    ) ?? [])
  );

  return (
    <section aria-labelledby="campus-entry-overview-title" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="campus-entry-overview-title" className="text-lg font-semibold text-slate-100">
            Campus Entry Overview
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Access decisions are shown separately from confirmed campus movements.
          </p>
        </div>
        {analytics && (
          <span className="text-[11px] text-slate-500">
            Campus time: {analytics.campus_timezone}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/[0.07] px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, icon: Icon, color }) => (
          <Card key={label} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium text-slate-400">{label}</p>
                <p className={`mt-2 text-xl font-semibold ${value === 'Not tracked' ? 'text-slate-500' : 'text-slate-100'}`}>
                  {value}
                </p>
              </div>
              <Icon className={`h-5 w-5 ${color}`} aria-hidden="true" />
            </div>
          </Card>
        ))}

        <Card className="p-4 sm:col-span-2 xl:col-span-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-slate-400">Campus Occupancy</p>
              <p className="mt-1 text-lg font-semibold text-slate-500">Not tracked</p>
              <p className="mt-1 text-xs text-slate-400">
                {analytics?.movement_limitation ?? 'No confirmed person-crossing events are available.'}
              </p>
            </div>
            <Activity className="h-5 w-5 text-indigo-300" aria-hidden="true" />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-white/[0.06] pt-3 text-xs text-slate-500">
            {(analytics?.supported_person_categories ?? ['student', 'staff', 'visitor', 'contractor']).map((category) => (
              <span key={category}>{formatCategory(category)}: —</span>
            ))}
            {!analytics?.supported_person_categories.includes('faculty') && (
              <span>Faculty: not a separate category in this data model</span>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="p-4 xl:col-span-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Gate Authorizations by Hour</h3>
              <p className="mt-1 text-xs text-slate-400">
                Allowed access attempts only; these are not confirmed entries or exits.
              </p>
            </div>
            <Clock3 className="h-4 w-4 text-indigo-300" aria-hidden="true" />
          </div>
          <div className="mt-5 flex h-32 items-end gap-1" role="img" aria-label="Hourly allowed entry and exit access authorizations">
            {(analytics?.hourly_activity ?? []).map((hour) => {
              const entries = hour.entry_authorizations;
              const exits = hour.exit_authorizations;
              const total = entries + exits;
              const height = total === 0 ? 2 : Math.max(5, (total / maxAuthorizationCount) * 100);
              return (
                <div key={hour.hour} className="group relative flex h-full min-w-0 flex-1 items-end">
                  <div
                    className="flex w-full flex-col justify-end overflow-hidden rounded-t-sm bg-violet-400/80"
                    style={{ height: `${height}%` }}
                    title={`${hour.hour.toString().padStart(2, '0')}:00 — ${entries} entry and ${exits} exit authorizations`}
                  >
                    {total > 0 && (
                      <div
                        className="w-full bg-emerald-400/90"
                        style={{ height: `${(entries / total) * 100}%` }}
                      />
                    )}
                  </div>
                  {hour.hour % 6 === 0 && (
                    <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] text-slate-500">
                      {hour.hour.toString().padStart(2, '0')}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-8 flex gap-4 text-[11px] text-slate-400">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-emerald-400" />Entry authorization</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-violet-400" />Exit authorization</span>
          </div>
        </Card>

        <Card className="p-4 xl:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Recent Gate Activity</h3>
              <p className="mt-1 text-xs text-slate-400">
                Access decisions only; manual commands and physical movements are not recorded here.
              </p>
            </div>
            <Activity className="h-4 w-4 text-cyan-300" aria-hidden="true" />
          </div>
          <div className="mt-3 max-h-64 space-y-2 overflow-y-auto">
            {analytics?.recent_activity.length ? analytics.recent_activity.map((event) => (
              <div key={event.id} className="flex items-center justify-between gap-3 border-t border-white/[0.05] py-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-slate-200">
                    {event.person_name || 'Unidentified'}{event.person_category ? ` · ${formatCategory(event.person_category)}` : ''}
                  </p>
                  <p className="mt-0.5 text-[10px] text-slate-500">
                    {event.direction} · {new Date(event.timestamp).toLocaleString(undefined, {
                      timeZone: analytics.campus_timezone,
                    })}
                  </p>
                </div>
                <span className={`shrink-0 rounded px-2 py-1 text-[10px] font-semibold ${
                  event.decision === 'DENY'
                    ? 'bg-rose-500/10 text-rose-300'
                    : event.decision === 'ALLOW'
                      ? 'bg-emerald-500/10 text-emerald-300'
                      : 'bg-amber-500/10 text-amber-300'
                }`}>
                  {event.decision === 'ALLOW' ? 'AUTHORIZED' : event.decision}
                </span>
              </div>
            )) : (
              <p className="py-6 text-center text-xs text-slate-500">
                {isLoading ? 'Loading access activity…' : 'No access activity recorded.'}
              </p>
            )}
          </div>
        </Card>
      </div>
    </section>
  );
}
