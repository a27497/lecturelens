import { shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import CourseTechnicalPanel from "./CourseTechnicalPanel.vue";
import type { ResultAiCallRecord, TaskResultResponse } from "../../types/result";

describe("CourseTechnicalPanel model calls", () => {
  it("renders multiple historical VLM records with null ids without duplicate-key warnings", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const calls = [historicalCall("provider-a", "model-a"), historicalCall("provider-b", "model-b")];
    const wrapper = shallowMount(CourseTechnicalPanel, {
      props: {
        taskId: "task_1",
        task: null,
        taskDetail: null,
        result: result(calls),
        connectionStatus: "connected",
        lastHeartbeatAt: "",
      },
      global: {
        stubs: {
          "el-empty": true,
          "el-tag": { template: "<span><slot /></span>" },
        },
      },
    });

    await wrapper.findAll("button").find((button) => button.text() === "模型调用")!.trigger("click");
    expect(wrapper.findAll(".call-list article")).toHaveLength(2);
    expect(wrapper.text()).toContain("provider-a / model-a");
    expect(wrapper.text()).toContain("provider-b / model-b");

    await wrapper.setProps({ result: result([...calls]) });
    expect(wrapper.findAll(".call-list article")).toHaveLength(2);
    expect(warn.mock.calls.flat().join(" ")).not.toContain("Duplicate keys");
    warn.mockRestore();
  });
});

function historicalCall(provider: string, model: string): ResultAiCallRecord {
  return {
    id: null,
    callType: "VLM",
    stage: "VISION_ANALYSIS",
    provider,
    model,
    status: "PARTIAL_SUCCESS",
    durationMillis: 25,
    providerDurationMillis: 20,
    batchCount: 5,
    retryCount: 0,
    promptTokens: null,
    completionTokens: null,
    totalTokens: null,
    inputUnits: 5,
    outputUnits: 4,
    createdAt: "2026-07-31T10:00:00",
  };
}

function result(aiCallRecords: ResultAiCallRecord[]): TaskResultResponse {
  return {
    taskId: "task_1",
    targetLanguage: "zh-CN",
    translationStatus: "SUCCEEDED",
    translationErrorSummary: null,
    sourceFullText: "",
    sourceParagraphs: [],
    translatedFullText: "",
    subtitles: [],
    translations: [],
    learningPackage: null,
    artifacts: [],
    keyframes: [],
    videoSegments: [],
    aiCallRecords,
  };
}
