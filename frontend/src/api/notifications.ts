// SmartGuard AI — Phase 4 Notification Log API Client
import apiClient from './client';

export type NotificationStatus = 'PENDING' | 'SENDING' | 'SENT' | 'FAILED' | 'RETRY_SCHEDULED';
export type NotificationType = 'ALERT' | 'DAILY_SUMMARY' | 'TEST';

export interface NotificationLogItem {
  id: string;
  notification_type: NotificationType;
  alert_id: string | null;
  contact_id: string | null;
  recipient_email: string;
  subject: string;
  status: NotificationStatus;
  attempt_count: number;
  max_attempts: number;
  created_at: string;
  last_attempted_at: string | null;
  sent_at: string | null;
  next_retry_at: string | null;
  provider: string | null;
  provider_message_id: string | null;
  error_detail: string | null;
  summary_date: string | null;
}

export interface NotificationListResponse {
  items: NotificationLogItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface NotificationFilterParams {
  status?: string;
  notification_type?: string;
  recipient?: string;
  date_from?: string;
  date_to?: string;
  skip?: number;
  limit?: number;
}

export const notificationsApi = {
  listNotifications: async (params?: NotificationFilterParams): Promise<NotificationListResponse> => {
    const res = await apiClient.get<NotificationListResponse>('/admin/notifications', { params });
    return res.data;
  },

  retryNotification: async (id: string): Promise<NotificationLogItem> => {
    const res = await apiClient.post<NotificationLogItem>(`/admin/notifications/${id}/retry`);
    return res.data;
  },

  retryAllFailed: async (): Promise<{ rescheduled: number }> => {
    const res = await apiClient.post<{ rescheduled: number }>('/admin/notifications/retry-all');
    return res.data;
  },
};

export default notificationsApi;
