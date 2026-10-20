// SmartGuard AI — Accounts API module
import apiClient from './client';
import type {
  AccountCreate,
  AccountListResponse,
  AccountStatusUpdate,
  PasswordResetRequest,
  Account,
} from '../types';

export const accountsApi = {
  list: async (params?: {
    search?: string;
    role?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }): Promise<AccountListResponse> => {
    const response = await apiClient.get<AccountListResponse>('/admin/accounts', { params });
    return response.data;
  },

  create: async (data: AccountCreate): Promise<Account> => {
    const response = await apiClient.post<Account>('/admin/accounts', data);
    return response.data;
  },

  updateStatus: async (id: string, data: AccountStatusUpdate): Promise<Account> => {
    const response = await apiClient.patch<Account>(`/admin/accounts/${id}/status`, data);
    return response.data;
  },

  resetPassword: async (id: string, data: PasswordResetRequest): Promise<Account> => {
    const response = await apiClient.post<Account>(`/admin/accounts/${id}/reset-password`, data);
    return response.data;
  },
};
