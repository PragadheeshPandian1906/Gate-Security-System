// SmartGuard AI — Phase 4 Alerts API Client
import apiClient from './client';

export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RESOLVED' | 'DISMISSED';

export interface AlertSummary {
  id: string;
  category: string;
  severity: AlertSeverity;
  title: string;
  status: AlertStatus;
  detected_plate: string | null;
  person_id: string | null;
  vehicle_id: string | null;
  access_attempt_id: string | null;
  first_detected_at: string;
  last_updated_at: string;
  occurrence_count: number;
}

export interface AlertNote {
  id: string;
  alert_id: string;
  author_id: string | null;
  note_type: 'NOTE' | 'STATUS_CHANGE' | 'ASSIGNMENT' | 'SYSTEM';
  body: string;
  created_at: string;
}

export interface AlertDetail extends AlertSummary {
  description: string | null;
  watchlist_entry_id: string | null;
  related_attempt_ids: string[] | null;
  assigned_to: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_reason: string | null;
  notes: AlertNote[];
}

export interface AlertMetrics {
  open: number;
  acknowledged: number;
  investigating: number;
  resolved: number;
  dismissed: number;
  critical_high_unresolved: number;
  total_unresolved: number;
}

export interface AlertListResponse {
  items: AlertSummary[];
  total: number;
  skip: number;
  limit: number;
}

export interface AlertFilterParams {
  category?: string;
  severity?: string;
  status?: string;
  plate?: string;
  skip?: number;
  limit?: number;
}

export const alertsApi = {
  getMetrics: async (): Promise<AlertMetrics> => {
    const res = await apiClient.get<AlertMetrics>('/alerts/metrics');
    return res.data;
  },

  listAlerts: async (params?: AlertFilterParams): Promise<AlertListResponse> => {
    const res = await apiClient.get<AlertListResponse>('/alerts', { params });
    return res.data;
  },

  getAlert: async (id: string): Promise<AlertDetail> => {
    const res = await apiClient.get<AlertDetail>(`/alerts/${id}`);
    return res.data;
  },

  acknowledgeAlert: async (id: string, reason?: string): Promise<AlertDetail> => {
    const res = await apiClient.post<AlertDetail>(`/alerts/${id}/acknowledge`, { reason });
    return res.data;
  },

  investigateAlert: async (id: string, reason?: string): Promise<AlertDetail> => {
    const res = await apiClient.post<AlertDetail>(`/alerts/${id}/investigate`, { reason });
    return res.data;
  },

  addNote: async (id: string, note: string): Promise<AlertDetail> => {
    const res = await apiClient.post<AlertDetail>(`/alerts/${id}/notes`, { note });
    return res.data;
  },

  resolveAlert: async (id: string, reason: string): Promise<AlertDetail> => {
    const res = await apiClient.post<AlertDetail>(`/alerts/${id}/resolve`, { reason });
    return res.data;
  },

  dismissAlert: async (id: string, reason: string): Promise<AlertDetail> => {
    const res = await apiClient.post<AlertDetail>(`/alerts/${id}/dismiss`, { reason });
    return res.data;
  },
};

export default alertsApi;
