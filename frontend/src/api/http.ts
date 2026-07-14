import axios, { AxiosError, type AxiosRequestConfig } from "axios";
import { ElMessage } from "element-plus";
import { clearAuthTokens } from "./authToken";
import { AUTH_EXPIRED_MESSAGE } from "../utils/errorMessage";

const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "";

const AUTH_INVALID_CODES = new Set([
  "AUTH_TOKEN_EXPIRED",
  "AUTH_TOKEN_INVALID",
  "COMMON_UNAUTHORIZED",
  "COMMON_FORBIDDEN",
]);

type AuthInvalidHandler = () => void;

let authInvalidHandler: AuthInvalidHandler | null = null;
let authInvalidNoticeShown = false;

export function setAuthInvalidHandler(handler: AuthInvalidHandler) {
  authInvalidHandler = handler;
}

function isLocalHostName(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function resolveApiBaseUrl(): string | undefined {
  if (!rawApiBaseUrl) {
    return undefined;
  }
  if (typeof window === "undefined") {
    return rawApiBaseUrl;
  }
  try {
    const configured = new URL(rawApiBaseUrl, window.location.origin);
    if (isLocalHostName(configured.hostname) && !isLocalHostName(window.location.hostname)) {
      if (import.meta.env.DEV) {
        console.warn(
          "[LectureLens API] Ignoring localhost VITE_API_BASE_URL for remote browser access.",
          {
            configuredBaseURL: redactUrl(rawApiBaseUrl),
            pageHost: window.location.host,
          },
        );
      }
      return undefined;
    }
  } catch {
    if (import.meta.env.DEV) {
      console.warn("[LectureLens API] Invalid VITE_API_BASE_URL; using Vite /api proxy.", {
        configuredBaseURL: redactUrl(rawApiBaseUrl),
      });
    }
    return undefined;
  }
  return rawApiBaseUrl;
}

function redactUrl(value: string | undefined): string | undefined {
  if (!value) {
    return value;
  }
  try {
    const url = new URL(value, window.location.origin);
    url.username = "";
    url.password = "";
    ["apiKey", "api_key", "token", "access_token", "secret", "password"].forEach((key) => {
      if (url.searchParams.has(key)) {
        url.searchParams.set(key, "[redacted]");
      }
    });
    return url.toString();
  } catch {
    return value.replace(/(api[-_]?key|access[-_]?token|token|secret|password)=([^&]+)/gi, "$1=[redacted]");
  }
}

function responseErrorCode(error: AxiosError): string {
  const data = error.response?.data;
  if (typeof data === "object" && data !== null && "code" in data) {
    const code = (data as { code?: unknown }).code;
    return typeof code === "string" ? code : "";
  }
  return "";
}

function requestUrl(config: AxiosRequestConfig | undefined): string {
  const baseURL = config?.baseURL || "";
  const url = config?.url || "";
  if (!baseURL) {
    return url;
  }
  try {
    return new URL(url, baseURL).toString();
  } catch {
    return `${baseURL}${url}`;
  }
}

function requestPath(config: AxiosRequestConfig | undefined): string {
  const url = requestUrl(config);
  try {
    const base = typeof window === "undefined" ? "http://courselingo.local" : window.location.origin;
    return new URL(url, base).pathname;
  } catch {
    return url.split("?")[0] || "";
  }
}

function isAuthEntryEndpoint(config: AxiosRequestConfig | undefined): boolean {
  const path = requestPath(config);
  return path === "/api/auth/login" || path === "/api/auth/register";
}

function isAuthInvalidError(error: AxiosError): boolean {
  if (isAuthEntryEndpoint(error.config)) {
    return false;
  }
  const status = error.response?.status;
  return status === 401 || status === 403 || AUTH_INVALID_CODES.has(responseErrorCode(error));
}

function loginRedirectUrl(): string {
  if (typeof window === "undefined") {
    return "/login";
  }
  if (window.location.pathname === "/login") {
    return "/login";
  }
  const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/login?redirect=${encodeURIComponent(redirect)}`;
}

function handleAuthInvalidation() {
  clearAuthTokens();
  authInvalidHandler?.();

  if (authInvalidNoticeShown || typeof window === "undefined") {
    return;
  }

  authInvalidNoticeShown = true;
  ElMessage.error(AUTH_EXPIRED_MESSAGE);

  const nextUrl = loginRedirectUrl();
  if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
    window.location.assign(nextUrl);
  }
}

export const http = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 30_000,
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (isAuthInvalidError(error)) {
      handleAuthInvalidation();
    }

    if (!error.response && import.meta.env.DEV) {
      console.warn("[LectureLens API] Network request failed", {
        url: redactUrl(requestUrl(error.config)),
        baseURL: redactUrl(error.config?.baseURL || http.defaults.baseURL),
        method: error.config?.method,
        timeout: error.config?.timeout,
        hasResponse: false,
      });
    }
    return Promise.reject(error);
  },
);
