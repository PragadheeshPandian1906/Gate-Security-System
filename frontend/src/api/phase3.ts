// SmartGuard AI — Phase 3 API Client
// Access decisions, gate simulation, schedules, watchlist
import apiClient from './client';

// ── Types ──────────────────────────────────────────────────────────────────

export type Direction = 'ENTRY' | 'EXIT';
export type Decision = 'ALLOW' | 'DENY' | 'MANUAL_REVIEW';
export type GateState = 'OPEN' | 'CLOSED' | 'MANUAL_REVIEW' | 'MANUAL_LATCHED_OPEN';
export type WatchlistSeverity = 'low' | 'medium' | 'high';

export interface AccessFaceContext {
  result: string | null;
  confidence: number | null;
  matched_person: { id: string; full_name: string; status: string; person_type: string } | null;
}

export interface AccessPlateContext {
  detected_plate: string | null;
  detected_plate_normalized: string | null;
  matched_vehicle: {
    id: string;
    plate_number: string;
    plate_normalized: string;
    status: string;
    owner_person_id: string | null;
    owner_name: string | null;
  } | null;
}

export interface ScheduleContext {
  ok: boolean | null;
  reason_code: string | null;
  detail: string | null;
  evaluated_local: string | null;
  weekday: string | null;
  schedule_open_time: string | null;
  schedule_close_time: string | null;
  campus_timezone: string | null;
}

export interface WatchlistContext {
  hit: boolean | null;
  severity: string | null;
  reason_code: string | null;
  reason_text: string | null;
  entry_id: string | null;
  entry_reason: string | null;
}

export interface AccessAttemptResponse {
  attempt_id: string;
  direction: Direction;
  decision: Decision;
  gate_result: GateState;
  reason_codes: string[];
  reason_text: string;
  face: AccessFaceContext;
  plate: AccessPlateContext;
  ownership_ok: boolean | null;
  schedule: ScheduleContext | null;
  watchlist: WatchlistContext | null;
  processing_ms: number;
}

export interface AccessAttemptSummary {
  id: string;
  timestamp: string;
  direction: Direction;
  decision: Decision;
  gate_result: GateState;
  reason_codes: string[] | null;
  reason_text: string | null;
  detected_plate: string | null;
  matched_person_id: string | null;
  matched_vehicle_id: string | null;
  person_status: string | null;
  vehicle_status: string | null;
  ownership_ok: boolean | null;
  schedule_ok: boolean | null;
  watchlist_hit: boolean | null;
  watchlist_severity: string | null;
  review_required: boolean;
  review_resolved: boolean;
  review_resolution: string | null;
  review_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  initiated_by: string | null;
  processing_ms: number | null;
}

export interface CampusHourlyAuthorization {
  hour: number;
  entry_authorizations: number;
  exit_authorizations: number;
}

export interface CampusAccessActivity {
  id: string;
  timestamp: string;
  person_name: string | null;
  person_category: string | null;
  direction: string;
  decision: Decision;
  movement_status: 'NOT_VERIFIED';
}

export interface CampusAnalytics {
  campus_timezone: string;
  movement_tracking_available: false;
  movement_limitation: string;
  total_entries_today: number | null;
  currently_inside: number | null;
  total_exits_today: number | null;
  denied_access_today: number;
  occupancy_by_category: Record<string, number> | null;
  supported_person_categories: string[];
  hourly_activity: CampusHourlyAuthorization[];
  recent_activity: CampusAccessActivity[];
}

export interface GateStatus {
  state: GateState;
  last_decision: string | null;
  last_direction: string | null;
  last_attempt_id: string | null;
  last_transition_at: string | null;
  simulation_note: string;
  iot_controller?: IotControllerStatus;
}

export interface ScheduleEntry {
  id?: string;
  weekday: string;
  is_open: boolean;
  open_time: string | null;
  close_time: string | null;
  campus_timezone: string;
}

export interface ScheduleResponse {
  entries: ScheduleEntry[];
  campus_timezone: string;
  current_local_time: string;
  today_weekday: string;
  today_is_open: boolean;
  today_open_time: string | null;
  today_close_time: string | null;
}

export interface WatchlistEntry {
  id: string;
  vehicle_id: string | null;
  plate_raw: string | null;
  plate_normalized: string | null;
  reason: string;
  severity: WatchlistSeverity;
  is_active: boolean;
  expires_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
  created_by: string | null;
  resolved_by: string | null;
}

// ── Access Attempts API ────────────────────────────────────────────────────

export const accessApi = {
  getCampusAnalytics: (signal?: AbortSignal) =>
    apiClient.get<CampusAnalytics>('/access/analytics/campus', { signal }),

  createAttempt: (data: {
    direction: Direction;
    face_verification_id?: string | null;
    alpr_verification_id?: string | null;
  }) => apiClient.post<AccessAttemptResponse>('/access/attempts', data),

  listAttempts: (params?: {
    skip?: number;
    limit?: number;
    direction?: Direction;
    decision?: Decision;
  }) => apiClient.get<AccessAttemptSummary[]>('/access/attempts', { params }),

  getAttempt: (id: string) =>
    apiClient.get<AccessAttemptSummary>(`/access/attempts/${id}`),

  getPendingReviews: (limit = 50) =>
    apiClient.get<AccessAttemptSummary[]>('/access/pending-reviews', { params: { limit } }),

  resolveReview: (id: string, data: { resolution: 'approved' | 'denied'; reason: string }) =>
    apiClient.post<{ success: boolean; message: string; new_gate_result: string | null }>(
      `/access/attempts/${id}/resolve`,
      data
    ),
};

export interface IotControllerStatus {
  is_connected: boolean;
  is_healthy: boolean;
  device_id: string | null;
  client_ip: string | null;
  connected_at: string | null;
  last_heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  reported_gate_state: 'CLOSED' | 'OPEN' | 'OPENING' | 'CLOSING' | 'UNKNOWN';
  reported_gate_mode: 'AUTOMATED' | 'MANUAL_LATCHED_OPEN' | 'UNKNOWN';
  configured_device_id: string;
  auto_close_duration_ms: number;
}

export interface IotSystemEvent {
  id: string;
  timestamp: string;
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR';
  source: 'ESP32' | 'BACKEND' | 'OPERATOR';
  event_type: string;
  message: string;
  details?: Record<string, any> | null;
}

export interface GateResetResponse {
  message: string;
  status: GateStatus;
  hardware: {
    connected: boolean;
    delivered: boolean;
    acknowledged: boolean;
    physical_position_confirmed: false;
    command_id: string | null;
    controller_state: string;
    status: string;
    error: string | null;
  };
}

export interface GateCommandResponse {
  message: string;
  status: GateStatus;
  hardware: {
    accepted: boolean;
    success: boolean;
    delivered: boolean;
    controller_acknowledged: boolean;
    physical_position_confirmed: false;
    command_id: string | null;
    status: string;
    detail: string | null;
    error: string | null;
  };
}

// ── Gate API ───────────────────────────────────────────────────────────────

export const gateApi = {
  getStatus: () => apiClient.get<GateStatus>('/gate/status'),
  reset: () => apiClient.post<GateResetResponse>('/gate/reset'),
  open: () => apiClient.post<GateCommandResponse>('/gate/open'),
  close: () => apiClient.post<GateCommandResponse>('/gate/close'),
  getIotStatus: () => apiClient.get<IotControllerStatus>('/gate/iot/status'),
  getIotEvents: () => apiClient.get<IotSystemEvent[]>('/gate/iot/events'),
};

// ── Schedule API ───────────────────────────────────────────────────────────

export const scheduleApi = {
  get: () => apiClient.get<ScheduleResponse>('/access/schedule'),
  update: (data: { entries: ScheduleEntry[]; campus_timezone: string }) =>
    apiClient.put<ScheduleResponse>('/access/schedule', data),
};

// ── Watchlist API ──────────────────────────────────────────────────────────

export const watchlistApi = {
  list: (params?: { active_only?: boolean; skip?: number; limit?: number }) =>
    apiClient.get<WatchlistEntry[]>('/watchlist', { params }),

  create: (data: {
    vehicle_id?: string;
    plate_raw?: string;
    reason: string;
    severity?: WatchlistSeverity;
    expires_at?: string;
  }) => apiClient.post<WatchlistEntry>('/watchlist', data),

  update: (id: string, data: Partial<{
    reason: string;
    severity: WatchlistSeverity;
    is_active: boolean;
    expires_at: string;
    resolution_note: string;
  }>) => apiClient.patch<WatchlistEntry>(`/watchlist/${id}`, data),

  deactivate: (id: string) => apiClient.delete(`/watchlist/${id}`),
};
