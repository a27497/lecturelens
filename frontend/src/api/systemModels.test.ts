import { beforeEach, expect, it, vi } from "vitest";
import { http } from "./http";
import { ACCESS_TOKEN_KEYS } from "./authToken";
import { maskedKey, systemModelError, systemModels } from "./systemModels";

vi.mock("./http", () => ({ http: { request: vi.fn() } }));
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); localStorage.setItem(ACCESS_TOKEN_KEYS[0], "admin-token"); });

it("uses only administrator APIs and probes an immutable saved model identity without credentials", async () => {
  vi.mocked(http.request).mockResolvedValue({ data: { data: { ok: true } } });
  await systemModels.probe(12, 34);
  expect(http.request).toHaveBeenCalledExactlyOnceWith({ method: "post", url: "/api/admin/system-models/probes", headers: { Authorization: "Bearer admin-token" }, data: { expectedVersion: 12, modelId: 34 } });
  await systemModels.executions("task?other=unsafe");
  expect(vi.mocked(http.request).mock.calls.at(-1)![0].url).toBe("/api/admin/system-models/executions?taskId=task%3Fother%3Dunsafe");
});

it("never shows an unrecognized server or vendor message and masks only the allowed suffix", () => {
  expect(systemModelError({ response: { data: { message: "private-raw-vendor-message", code: "UNKNOWN" } } })).not.toContain("private-raw-vendor-message");
  expect(systemModelError({ response: { data: { code: "COMMON_FORBIDDEN" } } })).toContain("管理员");
  expect(maskedKey({ hasKey: true, keyLast4: "1234" })).toBe("••••1234");
  expect(maskedKey(undefined)).toBe("未设置");
});
