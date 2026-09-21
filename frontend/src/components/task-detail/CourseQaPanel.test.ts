import { flushPromises, mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import CourseQaPanel from "./CourseQaPanel.vue";
import { askCourseQa, getEvidenceIndexStatus } from "../../api/qa";

vi.mock("../../api/qa", () => ({ getEvidenceIndexStatus: vi.fn().mockResolvedValue({ status: "READY" }), askCourseQa: vi.fn(), toReadableCourseQaError: () => "error" }));

it("renders the exact cited text returned by the API and keeps its video timestamp", async () => {
  const snippet = "The emcee introduces maritime history; ie ot is a literal source example.";
  vi.mocked(askCourseQa).mockResolvedValue({
    recordId: "1", answer: "课程介绍海洋历史", usage: null,
    evidence: [{ sourceType: "OCR", sourceId: "2", startTimeMillis: 1234, endTimeMillis: 2345,
      timeText: "00:01", snippet, translatedSnippet: "", confidence: 0.95, evidenceId: "stable-id", revision: 2 }],
  });
  const wrapper = mount(CourseQaPanel, {
    props: { taskId: "task" },
    global: { stubs: {
      "el-input": { props: ["modelValue"], emits: ["update:modelValue"],
        template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
      "el-button": { template: "<button><slot /></button>" },
      "el-tag": { template: "<span><slot /></span>" },
      "el-alert": true, "el-empty": true,
    } },
  });
  await flushPromises();
  await wrapper.get("textarea").setValue("主要讲什么？");
  await wrapper.findAll("button")[0]!.trigger("click");
  await flushPromises();
  expect(wrapper.get(".evidence-item p").text()).toBe(snippet);
  await wrapper.findAll("button").find(button => button.text() === "跳到视频")!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234]]);
});


it("removes a previous answer when a new question fails", async () => {
  vi.mocked(askCourseQa).mockResolvedValueOnce({ recordId: "1", answer: "旧问题的回答", usage: null, evidence: [] })
    .mockRejectedValueOnce(new Error("retrieval unavailable"));
  const wrapper = mount(CourseQaPanel, {
    props: { taskId: "task" },
    global: { stubs: {
      "el-input": { props: ["modelValue"], emits: ["update:modelValue"],
        template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
      "el-button": { template: "<button><slot /></button>" },
      "el-tag": true, "el-alert": true, "el-empty": true,
    } },
  });
  await flushPromises();
  await wrapper.get("textarea").setValue("第一个问题");
  await wrapper.findAll("button")[0]!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("旧问题的回答");
  await flushPromises();
  await wrapper.get("textarea").setValue("第二个问题");
  await wrapper.findAll("button")[0]!.trigger("click");
  await flushPromises();
  expect(wrapper.find(".qa-answer").exists()).toBe(false);
  expect(wrapper.find("el-alert-stub").attributes("title")).toBe("error");
});

it("waits for background indexing and enables questions when ready", async () => {
  vi.useFakeTimers();
  vi.mocked(getEvidenceIndexStatus).mockResolvedValueOnce({ status: "INDEXING" } as never)
    .mockResolvedValueOnce({ status: "READY" } as never);
  const wrapper = mount(CourseQaPanel, {
    props: { taskId: "task" },
    global: { stubs: {
      "el-input": { props: ["modelValue"], emits: ["update:modelValue"],
        template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
      "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
      "el-tag": true, "el-alert": true, "el-empty": true,
    } },
  });
  try {
    await flushPromises();
    await wrapper.get("textarea").setValue("算法如何结束？");
    expect(wrapper.get('[role="status"]').text()).toContain("正在准备");
    expect(wrapper.findAll("button")[0]!.attributes("disabled")).toBeDefined();
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();
    expect(wrapper.get('[role="status"]').text()).toContain("已就绪");
    expect(wrapper.findAll("button")[0]!.attributes("disabled")).toBeUndefined();
  } finally {
    wrapper.unmount();
    vi.useRealTimers();
  }
});

it("does not show the old course index state after switching tasks", async () => {
  let resolveOld!: (value: never) => void;
  vi.mocked(getEvidenceIndexStatus).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValueOnce({ status: "FAILED" } as never);
  const wrapper = mount(CourseQaPanel, {
    props: { taskId: "old" },
    global: { stubs: { "el-input": true, "el-button": true, "el-tag": true, "el-alert": true, "el-empty": true } },
  });
  await wrapper.setProps({ taskId: "new" });
  await flushPromises();
  resolveOld({ status: "READY" } as never);
  await flushPromises();
  expect(wrapper.get('[role="status"]').text()).toContain("自动重试");
  wrapper.unmount();
});
