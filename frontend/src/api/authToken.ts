export const ACCESS_TOKEN_KEYS = [
  "courselingo.accessToken",
  "courselingo:accessToken",
  "accessToken",
  "auth.accessToken",
];

export const REFRESH_TOKEN_KEY = "courselingo.refreshToken";
export const USER_EMAIL_KEY = "courselingo.userEmail";

export class AccessTokenMissingError extends Error {
  constructor() {
    super("登录已失效，请重新登录");
    this.name = "AccessTokenMissingError";
  }
}

export function readAccessToken(): string {
  const token = readOptionalAccessToken();
  if (token) {
    return token;
  }
  throw new AccessTokenMissingError();
}

export function readOptionalAccessToken(): string {
  for (const key of ACCESS_TOKEN_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

export function authHeader(): { Authorization: string } {
  return {
    Authorization: `Bearer ${readAccessToken()}`,
  };
}

export function saveAuthTokens(accessToken: string, refreshToken: string, email: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEYS[0], accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  window.localStorage.setItem(USER_EMAIL_KEY, email);
}

export function clearAuthTokens() {
  ACCESS_TOKEN_KEYS.forEach((key) => window.localStorage.removeItem(key));
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_EMAIL_KEY);
}
