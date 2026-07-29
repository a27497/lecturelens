import { describe, expect, it } from "vitest";
import { shallowMount } from "@vue/test-utils";
import CourseContentPanel from "./CourseContentPanel.vue";
import CourseVisualEvidencePanel from "./CourseVisualEvidencePanel.vue";
import type { ResultKeyframe, TaskResultResponse } from "../../types/result";

describe("CourseContentPanel visual evidence", () => {
  it("does not show an empty visual evidence tab for a legacy task", () => {
    const wrapper = shallowMount(CourseContentPanel, {
      props: { taskId: "legacy_task", status: "SUCCEEDED", result: result([]) },
    });

    expect(wrapper.text()).not.toContain("画面证据");
    expect(wrapper.findComponent(CourseVisualEvidencePanel).exists()).toBe(false);
  });

  it("shows the visual tab, forwards seek, and falls back when evidence disappears", async () => {
    const wrapper = shallowMount(CourseContentPanel, {
      props: { taskId: "task_1", status: "SUCCEEDED", result: result([keyframe()]) },
    });
    const visualTab = wrapper.findAll("button").find((button) => button.text() === "画面证据");

    expect(visualTab).toBeDefined();
    await visualTab!.trigger("click");
    const panel = wrapper.findComponent(CourseVisualEvidencePanel);
    expect(panel.exists()).toBe(true);

    panel.vm.$emit("seek", 12_345);
    expect(wrapper.emitted("seek")).toEqual([[12_345]]);

    await wrapper.setProps({ result: result([]) });
    expect(wrapper.text()).not.toContain("画面证据");
    expect(wrapper.findComponent(CourseVisualEvidencePanel).exists()).toBe(false);
    expect(wrapper.find('button[aria-pressed="true"]').text()).toBe("中文译文");
  });

  it("opens visual evidence by default for a visual-only result", () => {
    const visualOnly = result([keyframe()]);
    visualOnly.sourceFullText = "";
    visualOnly.sourceParagraphs = [];
    visualOnly.translatedFullText = "";

    const wrapper = shallowMount(CourseContentPanel, {
      props: { taskId: "task_visual", status: "SUCCEEDED", result: visualOnly },
    });

    expect(wrapper.find('button[aria-pressed="true"]').text()).toBe("画面证据");
    expect(wrapper.findComponent(CourseVisualEvidencePanel).exists()).toBe(true);
  });
});

function result(keyframes: ResultKeyframe[]): TaskResultResponse {
  return {
    taskId: "task_1",
    targetLanguage: "zh-CN",
    sourceFullText: "Course source",
    sourceParagraphs: ["Course source"],
    translatedFullText: "课程译文",
    subtitles: [],
    translations: [],
    learningPackage: null,
    artifacts: [],
    keyframes,
    videoSegments: [],
    aiCallRecords: [],
  };
}

function keyframe(): ResultKeyframe {
  return {
    frameId: 9,
    timestampMillis: 12_345,
    timeText: "00:12.345",
    imageUrl: "/api/tasks/task_1/keyframes/9/image",
    changeScore: 0.42,
    selectReason: "SCENE_CHANGE",
    createdAt: "2026-07-29T10:00:00",
    ocr: null,
    visualAnalysis: null,
  };
}
