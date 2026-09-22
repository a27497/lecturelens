import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCESS_TOKEN_KEYS, USER_EMAIL_KEY, authHeader, checkAuthSession, clearAuthTokens,
  installAuthSessionBoundary, saveAuthTokens } from "./authToken";

let dispose: (() => void) | undefined;
beforeEach(() => { localStorage.clear(); });
afterEach(() => { dispose?.(); });

describe("document authentication boundary", () => {
  it("a stale logout or login completion cannot replace another tab's credentials", () => {
    saveAuthTokens("A", "refresh", "a@example.test");
    const reset = vi.fn();
    dispose = installAuthSessionBoundary(reset);
    localStorage.setItem(ACCESS_TOKEN_KEYS[0], "B");
    clearAuthTokens();
    expect(localStorage.getItem(ACCESS_TOKEN_KEYS[0])).toBe("B");
    expect(() => saveAuthTokens("C", "refresh", "c@example.test")).toThrow();
    expect(localStorage.getItem(ACCESS_TOKEN_KEYS[0])).toBe("B");
  });
  it.each(ACCESS_TOKEN_KEYS)("fences old callbacks when %s changes before storage dispatch", (key) => {
    localStorage.setItem(key, "A");
    const reset = vi.fn();
    dispose = installAuthSessionBoundary(reset);
    localStorage.setItem(key, "B");
    expect(() => authHeader()).toThrow("登录已失效");
    expect(reset).toHaveBeenCalledExactlyOnceWith("/login");
    expect(localStorage.getItem(key)).toBe("B");
    window.dispatchEvent(new Event("storage"));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("invalidates cleared storage and restored pages but ignores unrelated changes", () => {
    saveAuthTokens("A", "refresh", "a@example.test");
    const reset = vi.fn();
    dispose = installAuthSessionBoundary(reset);
    localStorage.setItem("theme", "dark");
    window.dispatchEvent(new Event("storage"));
    expect(reset).not.toHaveBeenCalled();
    localStorage.clear();
    window.dispatchEvent(new Event("pageshow"));
    expect(reset).toHaveBeenCalledExactlyOnceWith("/login");
  });

  it("permits guest login and resets an authenticated demo transition", () => {
    const reset = vi.fn();
    dispose = installAuthSessionBoundary(reset);
    saveAuthTokens("A", "refresh", "a@example.test");
    expect(authHeader().Authorization).toBe("Bearer A");
    expect(reset).not.toHaveBeenCalled();
    saveAuthTokens("B", "refresh", "b@example.test", "/tasks/sample");
    expect(reset).toHaveBeenCalledExactlyOnceWith("/tasks/sample");
    expect(checkAuthSession()).toBe(false);
    expect(localStorage.getItem(USER_EMAIL_KEY)).toBe("b@example.test");
  });
});
