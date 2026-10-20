// SmartGuard AI — Phase 4 Security Contacts API Client
import apiClient from './client';

export interface SecurityContact {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  notify_categories: string[] | null;
  min_severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  daily_summary_enabled: boolean;
  created_at: string;
  updated_at: string;
  last_notified_at: string | null;
  last_notification_status: string | null;
}

export interface SecurityContactCreateInput {
  full_name: string;
  email: string;
  is_active?: boolean;
  notify_categories?: string[];
  min_severity?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  daily_summary_enabled?: boolean;
}

export interface SecurityContactUpdateInput {
  full_name?: string;
  email?: string;
  is_active?: boolean;
  notify_categories?: string[];
  min_severity?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  daily_summary_enabled?: boolean;
}

export interface EmailConfigStatus {
  email_enabled: boolean;
  email_provider: string;
  from_address: string;
  from_name: string;
  has_api_key: boolean;
}

export const contactsApi = {
  getConfigStatus: async (): Promise<EmailConfigStatus> => {
    const res = await apiClient.get<EmailConfigStatus>('/admin/security-contacts/config-status');
    return res.data;
  },

  listContacts: async (search?: string, is_active?: boolean): Promise<SecurityContact[]> => {
    const res = await apiClient.get<SecurityContact[]>('/admin/security-contacts', {
      params: { search, is_active },
    });
    return res.data;
  },

  getContact: async (id: string): Promise<SecurityContact> => {
    const res = await apiClient.get<SecurityContact>(`/admin/security-contacts/${id}`);
    return res.data;
  },

  createContact: async (data: SecurityContactCreateInput): Promise<SecurityContact> => {
    const res = await apiClient.post<SecurityContact>('/admin/security-contacts', data);
    return res.data;
  },

  updateContact: async (id: string, data: SecurityContactUpdateInput): Promise<SecurityContact> => {
    const res = await apiClient.put<SecurityContact>(`/admin/security-contacts/${id}`, data);
    return res.data;
  },

  deleteContact: async (id: string): Promise<void> => {
    await apiClient.delete(`/admin/security-contacts/${id}`);
  },

  sendTestEmail: async (id: string): Promise<{ message: string }> => {
    const res = await apiClient.post<{ message: string }>(`/admin/security-contacts/${id}/test-email`);
    return res.data;
  },
};

export default contactsApi;
