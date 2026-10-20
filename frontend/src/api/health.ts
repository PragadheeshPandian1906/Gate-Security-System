// SmartGuard AI — Health API module
import apiClient from './client';
import type { LivenessResponse, ReadinessResponse } from '../types';
import type { AxiosError } from 'axios';

let readinessRequest: Promise<ReadinessResponse> | null = null;

export const healthApi = {
  liveness: async (): Promise<LivenessResponse> => {
    const response = await apiClient.get<LivenessResponse>('/health/live');
    return response.data;
  },

  readiness: (): Promise<ReadinessResponse> => {
    if (!readinessRequest) {
      readinessRequest = apiClient
        .get<ReadinessResponse>('/health/ready')
        .then((response) => response.data)
        .catch((error: AxiosError<ReadinessResponse>) => {
          if (error.response?.status === 503 && error.response.data) {
            return error.response.data;
          }
          throw error;
        })
        .finally(() => {
          readinessRequest = null;
        });
    }
    return readinessRequest;
  },
};
