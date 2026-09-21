import { flushPromises, mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import CourseQaPanel from "./CourseQaPanel.vue";
import { askCourseQa } from "../../api/qa";

vi.mock("../../api/qa", () => ({ askCourseQa: vi.fn(), toReadableCourseQaError: () => "error" }));

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
  await wrapper.get("textarea").setValue("主要讲什么？");
  await wrapper.findAll("button")[0]!.trigger("click");
  await flushPromises();
  expect(wrapper.get(".evidence-item p").text()).toBe(snippet);
  await wrapper.findAll("button").find(button => button.text() === "跳到视频")!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234]]);
});
