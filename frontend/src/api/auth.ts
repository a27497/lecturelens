import { http } from "./http";
import { authHeader } from "./authToken";
import { toAuthEntryError } from "../utils/errorMessage";

export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
  timestamp: string;
  traceId: string;
}

export interface AuthUser {
  userId: number;
  email: string;
  status: string;
  role?: "ADMIN" | "USER";
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresIn: number;
  user: AuthUser;
}

export interface RegisterResponse {
  userId: number;
  email: string;
  status: string;
}

export async function login(request: LoginRequest): Promise<LoginResponse> {
  const response = await http.post<ApiResponse<LoginResponse>>("/api/auth/login", request);
  return response.data.data;
}

export async function currentUser(): Promise<AuthUser> {
  const response = await http.get<ApiResponse<AuthUser>>("/api/me", { headers: authHeader() });
  return response.data.data;
}

export async function register(request: RegisterRequest): Promise<RegisterResponse> {
  const response = await http.post<ApiResponse<RegisterResponse>>("/api/auth/register", request);
  return response.data.data;
}

export function toReadableAuthError(error: unknown): string {
  return toAuthEntryError(error);
}
