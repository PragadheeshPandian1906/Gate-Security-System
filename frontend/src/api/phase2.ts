// SmartGuard AI — People & Vehicles API Client (Phase 2)
import apiClient from './client';

// ── Types ──────────────────────────────────────────────────────────────────

export interface CampusPerson {
  id: string;
  full_name: string;
  person_type: 'staff' | 'student' | 'visitor' | 'contractor';
  employee_id: string | null;
  department: string | null;
  email: string | null;
  phone: string | null;
  status: 'active' | 'inactive' | 'suspended';
  notes: string | null;
  photo_path: string | null;
  photo_storage_path: string | null;
  created_at: string;
  updated_at: string;
  registered_by: string | null;
  face_profile_count: number;
}

export interface PersonListResponse {
  total: number;
  items: CampusPerson[];
}

export interface Vehicle {
  id: string;
  plate_number: string;
  plate_normalized: string;
  make: string | null;
  model: string | null;
  color: string | null;
  vehicle_type: string | null;
  owner_name: string | null;
  owner_person_id: string | null;
  status: 'active' | 'inactive' | 'flagged';
  notes: string | null;
  created_at: string;
  updated_at: string;
  registered_by: string | null;
}

export interface VehicleListResponse {
  total: number;
  items: Vehicle[];
}

export interface FaceVerifyResult {
  result: 'matched' | 'no_match' | 'low_confidence' | 'error' | 'no_face';
  confidence: number | null;
  distance: number | null;
  matched_person: { id: string; name: string } | null;
  faces_detected: number;
  candidates: Array<{ person_id: string; person_name: string; confidence: number; distance: number }>;
  verification_id: string | null;
  storage: { local_ok: boolean; remote_ok: boolean } | null;
  error: string | null;
}

export interface AlprVerifyResult {
  result: 'matched' | 'no_match' | 'no_plate' | 'error';
  detected_plate: string | null;
  detected_plate_normalized: string | null;
  detection_confidence: number | null;
  ocr_confidence: number | null;
  vehicle_match: {
    vehicle_id: string;
    plate_number: string;
    vehicle_status: string;
    owner_name: string | null;
    make: string | null;
    model: string | null;
    color: string | null;
  } | null;
  all_plates: Array<{ text: string; normalized: string; detection_confidence: number; ocr_confidence: number }>;
  verification_id: string | null;
  storage: { local_ok: boolean; remote_ok: boolean } | null;
  error: string | null;
}

export interface AiDiagnostics {
  system: { platform: string; python_version: string };
  gpu: { nvidia_smi: { available: boolean; gpus: Array<{ name: string; driver_version: string }> }; torch: { cuda_available: boolean; cuda_device_name: string | null } };
  onnxruntime: { available: boolean; version: string; providers: string[]; cuda_provider: boolean };
  insightface: { available: boolean; version?: string; cached_models?: string[]; error?: string };
  fast_alpr: { available: boolean; version?: string; error?: string };
  recommendation: { compute_device: string; execution_provider: string; face_recognition_ready: boolean; alpr_ready: boolean };
}

// ── People API ─────────────────────────────────────────────────────────────

export const peopleApi = {
  list: (params?: { skip?: number; limit?: number; person_type?: string; status?: string; search?: string }) =>
    apiClient.get<PersonListResponse>('/people', { params }),

  get: (id: string) => apiClient.get<CampusPerson>(`/people/${id}`),

  create: (data: {
    full_name: string;
    person_type: string;
    employee_id?: string;
    department?: string;
    email?: string;
    phone?: string;
    status?: string;
    notes?: string;
  }) => apiClient.post<CampusPerson>('/people', data),

  update: (id: string, data: Partial<CampusPerson>) =>
    apiClient.patch<CampusPerson>(`/people/${id}`, data),

  delete: (id: string) => apiClient.delete(`/people/${id}`),

  uploadPhoto: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<{ message: string; local_ok: boolean; remote_ok: boolean }>(
      `/people/${id}/photo`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  enrollFace: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<{ message: string; profile_id: string; faces_detected: number }>(
      `/people/${id}/enroll-face`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  listFaceProfiles: (id: string) =>
    apiClient.get<Array<{ id: string; person_id: string; embedding_model: string; is_primary: boolean; created_at: string }>>(`/people/${id}/faces`),
};

// ── Vehicles API ───────────────────────────────────────────────────────────

export const vehiclesApi = {
  list: (params?: { skip?: number; limit?: number; status?: string; search?: string }) =>
    apiClient.get<VehicleListResponse>('/vehicles', { params }),

  get: (id: string) => apiClient.get<Vehicle>(`/vehicles/${id}`),

  create: (data: {
    plate_number: string;
    make?: string;
    model?: string;
    color?: string;
    vehicle_type?: string;
    owner_name?: string;
    owner_person_id?: string;
    status?: string;
    notes?: string;
  }) => apiClient.post<Vehicle>('/vehicles', data),

  update: (id: string, data: Partial<Vehicle>) =>
    apiClient.patch<Vehicle>(`/vehicles/${id}`, data),

  delete: (id: string) => apiClient.delete(`/vehicles/${id}`),
};

export interface LivePersonSummary {
  id: string;
  name: string;
  person_type?: string | null;
  department?: string | null;
}

export interface LiveVehicleSummary {
  id: string;
  plate_number: string;
  status: string;
  owner_name?: string | null;
  owner_person_id?: string | null;
  make?: string | null;
  model?: string | null;
  color?: string | null;
}

export interface LiveFaceDetection {
  box: [number, number, number, number];
  score_type: string;
  score: number | null;
  distance: number | null;
  matched: boolean;
  status: 'matched' | 'unknown' | 'low_confidence' | 'no_enrolled' | 'detected_only';
  label: string;
  person: LivePersonSummary | null;
}

export interface LivePlateDetection {
  box: [number, number, number, number];
  plate_text: string | null;
  normalized_plate: string | null;
  detection_confidence: number | null;
  ocr_confidence: number | null;
  registered: boolean;
  status: 'registered' | 'unregistered' | 'flagged' | 'unreadable' | 'unavailable';
  label: string;
  vehicle: LiveVehicleSummary | null;
}

export interface LiveFrameResponse {
  frame_id: string;
  timestamp: number;
  image_width: number;
  image_height: number;
  faces: LiveFaceDetection[];
  plates: LivePlateDetection[];
  timing: {
    total_latency_ms: number;
    face_latency_ms: number;
    plate_latency_ms: number;
  };
  errors: {
    face_error: string | null;
    plate_error: string | null;
  };
  storage?: {
    local_ok: boolean;
    remote_ok: boolean;
    storage_path?: string | null;
    local_path?: string | null;
  } | null;
  face_verification_id?: string | null;
  alpr_verification_id?: string | null;
}

// ── AI Verification API ────────────────────────────────────────────────────

export const aiApi = {
  verifyFace: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<FaceVerifyResult>('/ai/verify-face', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000, // AI inference can take longer
    });
  },

  verifyPlate: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post<AlprVerifyResult>('/ai/verify-plate', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
  },

  processLiveFrame: (blob: Blob, frameId: string, timestamp: number, signal?: AbortSignal) => {
    const form = new FormData();
    form.append('file', blob, 'frame.jpg');
    form.append('frame_id', frameId);
    form.append('timestamp', timestamp.toString());
    return apiClient.post<LiveFrameResponse>('/ai/live-frame', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 15000,
      signal,
    });
  },

  saveSnapshot: (blob: Blob, note?: string) => {
    const form = new FormData();
    form.append('file', blob, 'snapshot.jpg');
    if (note) form.append('note', note);
    return apiClient.post<{
      success: boolean;
      filename: string;
      storage_path?: string | null;
      local_path?: string | null;
      local_ok: boolean;
      remote_ok: boolean;
    }>('/ai/save-snapshot', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  getDiagnostics: () => apiClient.get<AiDiagnostics>('/ai/diagnostics'),

  getFaceHistory: (limit = 20) =>
    apiClient.get<Array<{ id: string; result: string; confidence: number | null; matched_person_id: string | null; faces_detected: number; timestamp: string }>>('/ai/face-history', { params: { limit } }),

  getAlprHistory: (limit = 20) =>
    apiClient.get<Array<{ id: string; result: string; detected_plate: string | null; matched_vehicle_id: string | null; detection_confidence: number | null; timestamp: string }>>('/ai/alpr-history', { params: { limit } }),

  getStorageStats: () =>
    apiClient.get<{ 'face-images': { file_count: number; total_bytes: number }; 'access-evidence': { file_count: number; total_bytes: number }; supabase_available: boolean }>('/ai/storage-stats'),
};
