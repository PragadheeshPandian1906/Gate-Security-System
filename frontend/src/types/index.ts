// SmartGuard AI — TypeScript types for all API objects

export type Role = 'ADMIN' | 'SECURITY';
export type AccountStatus = 'active' | 'inactive';

export interface Account {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  status: AccountStatus;
  must_change_password: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: Account;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface AccountCreate {
  username: string;
  password: string;
  full_name: string;
  role: Role;
}

export interface AccountStatusUpdate {
  status: AccountStatus;
}

export interface PasswordResetRequest {
  new_password: string;
  must_change_password: boolean;
}

export interface AccountListResponse {
  accounts: Account[];
  total: number;
}

export interface LivenessResponse {
  status: string;
}

export interface ReadinessResponse {
  status: string;
  database: boolean;
  pgvector: boolean;
  environment?: string;
}

export interface ApiError {
  detail: string | { msg: string; type: string }[];
  message?: string;
}
