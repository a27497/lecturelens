import { describe, expect, it, vi } from "vitest";
import { flushPromises, shallowMount } from "@vue/test-utils";
import CourseContentPanel from "./CourseContentPanel.vue";
import CourseVisualEvidencePanel from "./CourseVisualEvidencePanel.vue";
import type { ResultKeyframe, TaskResultResponse } from "../../types/result";

describe("CourseContentPanel visual evidence", () => {
  it("shows a terminal translation failure instead of per-segment loading", async () => {
    const failed = result([]);
    failed.translatedFullText = "";
    failed.translationStatus = "FAILED";
    failed.translationErrorSummary = "翻译生成失败，请重新处理任务。";
    failed.subtitles = [{ segmentIndex: 0, startMillis: 0, endMillis: 1000, language: "en", sourceText: "hello" }];

    const wrapper = shallowMount(CourseContentPanel, {
      props: { taskId: "task_failed", status: "FAILED", result: failed },
      global: {
        stubs: {
          "el-empty": { props: ["description"], template: "<div>{{ description }}</div>" },
        },
      },
    });

    const translatedTab = wrapper.findAll("button").find((button) => button.text() === "中文译文");
    await translatedTab!.trigger("click");
    expect(wrapper.text()).toContain("翻译生成失败，请重新处理任务。");
    expect(wrapper.text()).not.toContain("译文生成中");
    const timelineTab = wrapper.findAll("button").find((button) => button.text() === "时间轴");
    await timelineTab!.trigger("click");
    expect(wrapper.text()).toContain("译文生成失败");
    expect(wrapper.text()).toContain("hello");
  });

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
    translationStatus: "SUCCEEDED",
    translationErrorSummary: null,
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

describe("course transcript position", () => {
  function setup() {
    const data = result([]);
    data.subtitles = [
      { segmentIndex: 3, startMillis: 1000, endMillis: 3000, language: "en", sourceText: "first passage" },
      { segmentIndex: 4, startMillis: 2000, endMillis: 2500, language: "en", sourceText: "overlap passage" },
      { segmentIndex: 5, startMillis: 5000, endMillis: 5000, language: "en", sourceText: "empty range" },
    ];
    return shallowMount(CourseContentPanel, { props: { taskId: "course", status: "SUCCEEDED", result: data, view: "timeline" as const, positionMs: 2100, visible: true }, global: { stubs: {
      "el-button": { props: ["disabled"], template: '<button :disabled="disabled"><slot /></button>' },
      "el-input": { props: ["modelValue"], emits: ["update:modelValue"], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
    } } });
  }
  it("highlights actual intervals, leaves gaps empty and disables empty ranges", async () => {
    const wrapper = setup();
    expect(wrapper.get('[aria-current="true"]').attributes("data-segment")).toBe("4");
    expect(wrapper.findAll(".timeline-row button")[2]!.attributes("disabled")).toBeDefined();
    await wrapper.setProps({ positionMs: 3500 });
    expect(wrapper.find('[aria-current="true"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("当前位置没有对应的原文片段");
    wrapper.unmount();
  });
  it.each(["wheel", "touchstart", "pointerdown"])("pauses on %s and explicitly resumes", async event => {
    const wrapper = setup();
    await wrapper.get(".timeline-list").trigger(event);
    expect(wrapper.get(".timeline-controls button").attributes("aria-pressed")).toBe("false");
    await wrapper.setProps({ positionMs: 1400 });
    expect(wrapper.get(".timeline-controls button").attributes("aria-pressed")).toBe("false");
    await wrapper.get(".timeline-controls button").trigger("click");
    expect(wrapper.get(".timeline-controls button").attributes("aria-pressed")).toBe("true");
    wrapper.unmount();
  });
  it("does not scroll during manual reading, search or while hidden", async () => {
    const wrapper = setup();
    const list = wrapper.get(".timeline-list").element as HTMLElement;
    vi.spyOn(list, "getBoundingClientRect").mockReturnValue({ top: 0, bottom: 100 } as DOMRect);
    for (const row of wrapper.findAll(".timeline-row")) vi.spyOn(row.element, "getBoundingClientRect").mockReturnValue({ top: 400, bottom: 500 } as DOMRect);
    await wrapper.get(".timeline-list").trigger("keydown", { key: "PageDown" });
    await wrapper.setProps({ positionMs: 1400 });
    expect(list.scrollTop).toBe(0);
    await wrapper.get("input").setValue("first");
    expect(wrapper.get(".timeline-controls button").attributes("aria-pressed")).toBe("false");
    await wrapper.setProps({ visible: false });
    await wrapper.get(".timeline-controls button").trigger("click");
    expect(list.scrollTop).toBe(0);
    await wrapper.setProps({ visible: true });
    await flushPromises();
    expect(list.scrollTop).toBeGreaterThan(0);
    wrapper.unmount();
  });
  it("does not fabricate translation alignment from segment number", async () => {
    const wrapper = setup();
    const data = result([]);
    data.subtitles = [{ segmentIndex: 3, startMillis: 1000, endMillis: 3000, language: "en", sourceText: "original" }];
    data.translations = [{ segmentIndex: 3, startMillis: 2000, endMillis: 4000, sourceLanguage: "en", targetLanguage: "zh", translatedText: "MISALIGNED" }];
    await wrapper.setProps({ result: data });
    expect(wrapper.text()).not.toContain("MISALIGNED");
    await wrapper.get(".timeline-row button").trigger("click");
    expect(wrapper.emitted("seek")).toEqual([[1000]]);
    wrapper.unmount();
  });
});

it("waits for result availability before falling back from a restored visual view", async () => {
  const wrapper = shallowMount(CourseContentPanel, { props: { taskId: "course", result: null, view: "visual" } });
  expect(wrapper.emitted("update:view")).toBeUndefined();
  await wrapper.setProps({ result: result([]) });
  expect(wrapper.emitted("update:view")).toEqual([["translated"]]);
  wrapper.unmount();
});

it("keeps the verified reference distinct from a later playback position", async () => {
  const data = result([]);
  data.subtitles = [
    { segmentIndex: 1, startMillis: 0, endMillis: 1000, language: "en", sourceText: "cited passage" },
    { segmentIndex: 2, startMillis: 1000, endMillis: 2000, language: "en", sourceText: "later playback" },
  ];
  const wrapper = shallowMount(CourseContentPanel, { props: { taskId: "course", result: data, view: "timeline", positionMs: 100, referenceMs: 100 } });
  expect(wrapper.get('[data-reference=true]').text()).toContain('cited passage');
  await wrapper.setProps({ positionMs: 1200 });
  expect(wrapper.get('[aria-current=true]').text()).toContain('later playback');
  expect(wrapper.get('[data-reference=true]').text()).toContain('cited passage');
  await wrapper.setProps({ referenceMs: undefined });
  expect(wrapper.find('[data-reference=true]').exists()).toBe(false);
  wrapper.unmount();
});
