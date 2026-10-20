// SmartGuard AI — Phase 4 Reports API Client
import apiClient from './client';

export interface AccessReportRow {
  id: string;
  timestamp: string;
  direction: 'ENTRY' | 'EXIT';
  decision: 'ALLOW' | 'DENY' | 'MANUAL_REVIEW';
  gate_result: 'OPEN' | 'CLOSED' | 'MANUAL_REVIEW';
  reason_codes: string[];
  reason_text: string | null;
  detected_plate: string | null;
  detected_plate_normalized: string | null;
  matched_person_id: string | null;
  person_status: string | null;
  matched_vehicle_id: string | null;
  vehicle_status: string | null;
  ownership_ok: boolean | null;
  schedule_ok: boolean | null;
  watchlist_hit: boolean | null;
  watchlist_severity: string | null;
  review_required: boolean;
  review_resolved: boolean;
  review_resolution: string | null;
  review_reason: string | null;
  initiated_by: string | null;
  processing_ms: number | null;
}

export interface AccessReportResponse {
  items: AccessReportRow[];
  total: number;
  skip: number;
  limit: number;
}

export interface AccessReportFilterParams {
  direction?: string;
  decision?: string;
  plate?: string;
  date_from?: string;
  date_to?: string;
  watchlist_only?: boolean;
  review_pending?: boolean;
  skip?: number;
  limit?: number;
}

export interface DailySummaryMetric {
  code: string;
  count: number;
}

export interface DailySummaryResponse {
  date: string;
  timezone: string;
  total: number;
  allowed: number;
  denied: number;
  manual_review: number;
  entry: number;
  exit: number;
  new_alerts: number;
  unresolved_alerts: number;
  watchlist_incidents: number;
  repeated_denials: number;
  pending_reviews: number;
  resolved_reviews: number;
  top_denial_reasons: DailySummaryMetric[];
}

export const reportsApi = {
  listAccessReport: async (params?: AccessReportFilterParams): Promise<AccessReportResponse> => {
    const res = await apiClient.get<AccessReportResponse>('/reports/access', { params });
    return res.data;
  },

  downloadCsv: async (params?: AccessReportFilterParams): Promise<Blob> => {
    const res = await apiClient.get('/reports/access/export', {
      params,
      responseType: 'blob',
    });
    return res.data;
  },

  getDailySummary: async (date?: string): Promise<DailySummaryResponse> => {
    const res = await apiClient.get<DailySummaryResponse>('/reports/daily-summary', {
      params: date ? { date } : undefined,
    });
    return res.data;
  },

  sendDailySummary: async (date: string, force: boolean = false): Promise<{ sent_count: number; skipped_count: number; failed_count: number; message?: string }> => {
    const res = await apiClient.post('/reports/daily-summary/send', { date, force });
    return res.data;
  },
};

export default reportsApi;
