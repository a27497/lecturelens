export const ACCESS_TOKEN_KEYS = [
  "courselingo.accessToken",
  "courselingo:accessToken",
  "accessToken",
  "auth.accessToken",
];

export const REFRESH_TOKEN_KEY = "courselingo.refreshToken";
export const USER_EMAIL_KEY = "courselingo.userEmail";

let sessionToken: string | undefined;
let sessionEmail = "";
let sessionInvalid = false;
let resetDocument: ((path: string) => void) | undefined;

// A document owns one authentication session. Reloading also discards pending
// uploads, downloads, signed media URLs and component/store caches together.
export function installAuthSessionBoundary(reset: (path: string) => void) {
  resetDocument = reset;
  sessionToken = readOptionalAccessToken();
  sessionEmail = window.localStorage.getItem(USER_EMAIL_KEY) || "";
  sessionInvalid = false;
  const check = () => { checkAuthSession(); };
  window.addEventListener("storage", check);
  window.addEventListener("pageshow", check);
  window.addEventListener("focus", check);
  document.addEventListener("visibilitychange", check);
  return () => {
    window.removeEventListener("storage", check);
    window.removeEventListener("pageshow", check);
    window.removeEventListener("focus", check);
    document.removeEventListener("visibilitychange", check);
    resetDocument = undefined;
    sessionToken = undefined;
    sessionInvalid = false;
  };
}

export function checkAuthSession(): boolean {
  if (sessionToken !== undefined && (sessionToken !== readOptionalAccessToken()
      || sessionEmail !== (window.localStorage.getItem(USER_EMAIL_KEY) || ""))) {
    endAuthDocument("/login");
  }
  return !sessionInvalid;
}

export function endAuthDocument(path: string) {
  if (!resetDocument || sessionInvalid) return;
  sessionInvalid = true;
  resetDocument(path);
}

export class AccessTokenMissingError extends Error {
  constructor() {
    super("登录已失效，请重新登录");
    this.name = "AccessTokenMissingError";
  }
}

export function readAccessToken(): string {
  if (!checkAuthSession()) throw new AccessTokenMissingError();
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

export function saveAuthTokens(accessToken: string, refreshToken: string, email: string, nextPath = "/upload") {
  if (!checkAuthSession()) throw new AccessTokenMissingError();
  window.localStorage.setItem(ACCESS_TOKEN_KEYS[0], accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  window.localStorage.setItem(USER_EMAIL_KEY, email);
  // Login starts from a guest document. Replacing an authenticated session
  // (including entry into the shared demo account) requires a fresh document.
  if (sessionToken) endAuthDocument(nextPath);
  else if (sessionToken !== undefined) {
    sessionToken = accessToken.trim();
    sessionEmail = email;
  }
}

export function clearAuthTokens() {
  if (!checkAuthSession()) return;
  ACCESS_TOKEN_KEYS.forEach((key) => window.localStorage.removeItem(key));
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_EMAIL_KEY);
}
