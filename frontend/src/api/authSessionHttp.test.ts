import { AxiosError } from "axios";
import { afterEach, expect, it, vi } from "vitest";
import { http } from "./http";
import { ACCESS_TOKEN_KEYS, authHeader, installAuthSessionBoundary, saveAuthTokens } from "./authToken";

let dispose: (() => void) | undefined;
afterEach(() => { dispose?.(); localStorage.clear(); });

it("discards late A responses and cannot clear B credentials on an old 401", async () => {
  saveAuthTokens("A", "refresh", "a@example.test");
  const reset = vi.fn();
  dispose = installAuthSessionBoundary(reset);
  let rejectRequest!: (error: Error) => void;
  let requestConfig: any;
  const request = http.get("/api/tasks/a", {
    headers: authHeader(),
    adapter: (config) => new Promise((_resolve, reject) => {
      requestConfig = config;
      rejectRequest = reject;
    }),
  });
  await vi.waitFor(() => expect(rejectRequest).toBeDefined());
  localStorage.setItem(ACCESS_TOKEN_KEYS[0], "B");
  rejectRequest(new AxiosError("expired", "ERR_BAD_REQUEST", requestConfig, undefined,
    { status: 401, statusText: "Unauthorized", headers: {}, config: requestConfig, data: {} }));
  await expect(request).rejects.toThrow();
  expect(reset).toHaveBeenCalledExactlyOnceWith("/login");
  expect(localStorage.getItem(ACCESS_TOKEN_KEYS[0])).toBe("B");
  const adapter = vi.fn();
  await expect(http.get("/api/uploads", { adapter })).rejects.toThrow("session changed");
  expect(adapter).not.toHaveBeenCalled();
});
