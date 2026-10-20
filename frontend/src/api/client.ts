// SmartGuard AI — Centralized Axios Client
// All API requests go through this client. Never put secrets here.

import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

if (!BASE_URL) {
  console.error('VITE_API_BASE_URL is not configured. Check frontend/.env');
}

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor: attach Bearer token ────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('sg_token');
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor: handle auth failures globally ────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Token expired or invalid — clear state and redirect to login
      localStorage.removeItem('sg_token');
      localStorage.removeItem('sg_user');
      // Avoid circular imports by using window.location directly
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;

// Helper to extract a human-readable error message
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((e: { msg: string }) => e.msg).join(', ');
    }
    if (error.message === 'Network Error') {
      return 'Cannot reach the server. Check that the backend is running.';
    }
    if (error.code === 'ECONNABORTED') {
      return 'Request timed out. Please try again.';
    }
    return error.message || 'An unexpected error occurred.';
  }
  return 'An unexpected error occurred.';
}

export const extractApiError = getErrorMessage;
