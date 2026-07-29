import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadTaskKeyframeImage, fetchTaskResult } from "./result";
import { http } from "./http";
import type { TaskResultResponse } from "../types/result";

vi.mock("./http", () => ({
  http: { get: vi.fn() },
}));

const httpGet = vi.mocked(http.get);

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("courselingo.accessToken", "access-token");
  httpGet.mockReset();
});

describe("task result API compatibility", () => {
  it("normalizes visual arrays omitted by an older response", async () => {
    const legacyResponse = {
      taskId: "legacy_task",
      targetLanguage: "zh-CN",
      sourceFullText: "legacy source",
      translatedFullText: "旧译文",
      learningPackage: null,
    } as TaskResultResponse;
    httpGet.mockResolvedValue({ data: { data: legacyResponse } });

    const result = await fetchTaskResult("legacy_task");

    expect(result).not.toBeNull();
    if (!result) throw new Error("normalized result is required");
    expect(result.keyframes).toEqual([]);
    expect(result.videoSegments).toEqual([]);
    expect(result.subtitles).toEqual([]);
    expect(result.translations).toEqual([]);
    expect(httpGet).toHaveBeenCalledWith("/api/tasks/legacy_task/results", {
      headers: { Authorization: "Bearer access-token" },
    });
  });

  it("normalizes a null result payload without creating a partial result", async () => {
    httpGet.mockResolvedValue({ data: { data: null } });

    await expect(fetchTaskResult("task_pending")).resolves.toBeNull();
  });

  it("propagates an authenticated keyframe image request failure", async () => {
    const failure = new Error("image request failed");
    const controller = new AbortController();
    httpGet.mockRejectedValue(failure);

    await expect(downloadTaskKeyframeImage("task_1", 9, controller.signal)).rejects.toBe(failure);
    expect(httpGet).toHaveBeenCalledWith("/api/tasks/task_1/keyframes/9/image", {
      headers: {
        Authorization: "Bearer access-token",
        Accept: "image/jpeg,image/*",
      },
      responseType: "blob",
      signal: controller.signal,
    });
  });
});
