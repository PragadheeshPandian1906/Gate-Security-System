// SmartGuard AI — Authentication API module
import apiClient from './client';
import type { LoginRequest, TokenResponse, Account } from '../types';

export const authApi = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/login', data);
    return response.data;
  },

  me: async (): Promise<Account> => {
    const response = await apiClient.get<Account>('/auth/me');
    return response.data;
  },
};
