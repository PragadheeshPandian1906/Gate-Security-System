// SmartGuard AI — Phase 5 Visitor Management API Client
import apiClient from './client';

// ── Types ──────────────────────────────────────────────────────────────────

export type VisitorPassStatus =
  | 'ISSUED'
  | 'PENDING_APPROVAL'
  | 'ACTIVE_INSIDE'
  | 'COMPLETED'
  | 'EXPIRED'
  | 'REVOKED'
  | 'DENIED';

export interface VisitorPersonResponse {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  department: string | null;
  notes: string | null;
  status: string;
  created_at: string;
}

export interface VisitorPassResponse {
  id: string;
  pass_number: string;
  visitor_id: string;
  visitor_name: string;
  visitor_email: string | null;
  visitor_phone: string | null;
  organization: string | null;
  host_id: string | null;
  host_name: string | null;
  vehicle_plate: string | null;
  purpose: string | null;
  valid_from: string;
  valid_until: string;
  status: VisitorPassStatus;
  check_in_at: string | null;
  check_in_by: string | null;
  check_out_at: string | null;
  check_out_by: string | null;
  email_sent: boolean;
  email_sent_at: string | null;
  email_delivery_status: string | null;
  revocation_reason: string | null;
  revoked_at: string | null;
  qr_storage_path: string | null;
  qr_code_path?: string | null;
  qr_code_base64?: string | null;
  qr_image_base64?: string | null;
  created_at: string;
}

export interface VisitorPassCreatedResponse extends VisitorPassResponse {
  raw_qr_token: string;
  qr_payload: string;
  qr_image_base64: string;
  qr_code_base64: string;
}

export interface VisitorApprovalResponse {
  id: string;
  pass_id: string;
  pass_number: string;
  visitor_id: string;
  visitor_name: string;
  visitor_email: string | null;
  visitor_phone: string | null;
  organization: string | null;
  host_name: string | null;
  vehicle_plate: string | null;
  purpose: string | null;
  direction: string;
  status: 'PENDING' | 'APPROVED' | 'DENIED' | 'CANCELLED';
  scanned_at: string;
  valid_from: string;
  valid_until: string;
  alert_id: string | null;
  schedule_status: string | null;
}

export interface VisitorScanResponse {
  status: 'PENDING_APPROVAL' | 'ACTIVE_INSIDE' | 'COMPLETED' | 'DENIED';
  message: string;
  pass_id?: string | null;
  pass_number?: string | null;
  visitor_name?: string | null;
  direction: 'ENTRY' | 'EXIT';
  approval_id?: string | null;
  gate_state: 'OPEN' | 'CLOSED';
}

export interface VisitorMetrics {
  active_passes: number;
  pending_approvals: number;
  visitors_inside: number;
  completed_today: number;
  revoked_or_expired: number;
}

export interface CreateVisitorPassPayload {
  visitor_id?: string;
  full_name?: string;
  phone?: string;
  email?: string;
  organization?: string;
  id_type?: string;
  id_number?: string;
  host_id?: string;
  purpose?: string;
  vehicle_plate?: string;
  valid_from: string;
  valid_until: string;
  notes?: string;
  send_email?: boolean;
}

export interface ScanPassPayload {
  qr_credential: string;
  direction?: 'ENTRY' | 'EXIT';
}

export interface ApprovalDecisionPayload {
  decision: 'APPROVE' | 'DENY';
  denial_reason?: string;
  notes?: string;
}

export interface RevokePassPayload {
  reason: string;
}

// ── API Methods ────────────────────────────────────────────────────────────

export const visitorsApi = {
  // Metrics
  getMetrics: async (): Promise<VisitorMetrics> => {
    const res = await apiClient.get<VisitorMetrics>('/visitors/passes/metrics');
    return res.data;
  },

  // Active visitors currently inside campus
  getActiveInside: async (): Promise<VisitorPassResponse[]> => {
    const res = await apiClient.get<VisitorPassResponse[]>('/visitors/passes/active-inside');
    return res.data;
  },

  // Pending security approvals
  getPendingApprovals: async (): Promise<VisitorApprovalResponse[]> => {
    const res = await apiClient.get<VisitorApprovalResponse[]>('/visitors/passes/pending-approvals');
    return res.data;
  },

  // Pre-register visitor & issue pass in one atomic step
  registerVisitor: async (payload: CreateVisitorPassPayload): Promise<VisitorPassCreatedResponse> => {
    const res = await apiClient.post<VisitorPassCreatedResponse>('/visitors/passes', payload);
    return res.data;
  },

  // Issue pass for existing visitor
  createPass: async (payload: CreateVisitorPassPayload): Promise<VisitorPassCreatedResponse> => {
    const res = await apiClient.post<VisitorPassCreatedResponse>('/visitors/passes', payload);
    return res.data;
  },

  // List all passes with optional filter
  getPasses: async (params?: {
    status?: string;
    visitor_id?: string;
    skip?: number;
    limit?: number;
  }): Promise<VisitorPassResponse[]> => {
    const res = await apiClient.get<VisitorPassResponse[]>('/visitors/passes', { params });
    return res.data;
  },

  // Single pass details
  getPass: async (passId: string): Promise<VisitorPassResponse> => {
    const res = await apiClient.get<VisitorPassResponse>(`/visitors/passes/${passId}`);
    return res.data;
  },

  // Scan & verify QR credential
  scanPass: async (payload: ScanPassPayload): Promise<VisitorScanResponse> => {
    const res = await apiClient.post<VisitorScanResponse>('/visitors/scan', payload);
    return res.data;
  },

  // Officer explicit approval / denial
  decideApproval: async (
    approvalId: string,
    payload: ApprovalDecisionPayload
  ): Promise<VisitorPassResponse> => {
    const res = await apiClient.post<VisitorPassResponse>(
      `/visitors/approvals/${approvalId}/decision`,
      payload
    );
    return res.data;
  },

  // Revoke an eligible pass
  revokePass: async (passId: string, payload: RevokePassPayload): Promise<VisitorPassResponse> => {
    const res = await apiClient.post<VisitorPassResponse>(
      `/visitors/passes/${passId}/revoke`,
      payload
    );
    return res.data;
  },

  // Resend pass email via Phase 4 Brevo gateway
  resendEmail: async (passId: string): Promise<{ message: string; status: string }> => {
    const res = await apiClient.post<{ message: string; status: string }>(
      `/visitors/passes/${passId}/resend-email`
    );
    return res.data;
  },

  // Search existing visitor directory
  getVisitors: async (params?: { query?: string; limit?: number }): Promise<VisitorPersonResponse[]> => {
    const res = await apiClient.get<VisitorPersonResponse[]>('/visitors/people', { params });
    return res.data;
  },

  // Visitor visit history
  getVisitorHistory: async (personId: string): Promise<VisitorPassResponse[]> => {
    const res = await apiClient.get<VisitorPassResponse[]>(
      `/visitors/people/${personId}/history`
    );
    return res.data;
  },
};

export default visitorsApi;
