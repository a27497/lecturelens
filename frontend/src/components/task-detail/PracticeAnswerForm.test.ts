import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import PracticeAnswerForm from "./PracticeAnswerForm.vue";
import { studyCommand } from "../../api/study";
import type { StudyAttempt, StudyResponse } from "../../api/study";

vi.mock("../../api/study", () => ({ studyCommand: vi.fn() }));
const props = { taskId: "course", sessionId: "session", runId: "run", artifactId: "artifact", questionIndex: 0 };
const saved: StudyAttempt = { attempt_id: "attempt", artifact_id: "artifact", question_index: 0, version: 1, answer_text: "my answer", created_at: "2026-09-20T00:00:00Z" };
const stubs = {
  "el-input": { props: ["modelValue", "disabled"], emits: ["update:modelValue"], template: `<textarea :disabled="disabled" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
};
const render = (attempt?: StudyAttempt) => mount(PracticeAnswerForm, { props: { ...props, attempt }, global: { stubs } });
beforeEach(() => vi.resetAllMocks());

it("saves a scoped real answer and restores the version after remount", async () => {
  vi.mocked(studyCommand).mockResolvedValue({ attempt: saved });
  const wrapper = render();
  expect(wrapper.find("button").attributes("disabled")).toBeDefined();
  await wrapper.find("textarea").setValue("my answer");
  await wrapper.find("button").trigger("click");
  await flushPromises();
  expect(studyCommand).toHaveBeenCalledWith("course", expect.objectContaining({ operation: "SAVE_ATTEMPT", run_id: "run", artifact_id: "artifact", question_index: 0, expected_version: 0, answer_text: "my answer" }));
  expect(wrapper.emitted("saved")).toEqual([[saved]]);
  wrapper.unmount();
  const restored = render(saved);
  expect(restored.find("textarea").element.value).toBe("my answer");
  expect(restored.text()).toContain("已保存第 1 版");
  restored.unmount();
});

it("retries an unconfirmed save with the same key and preserves input", async () => {
  vi.mocked(studyCommand).mockRejectedValue(new Error("offline"));
  const wrapper = render();
  await wrapper.find("textarea").setValue("my answer");
  await wrapper.find("button").trigger("click"); await flushPromises();
  const first = vi.mocked(studyCommand).mock.calls[0]![1];
  expect(wrapper.find("textarea").element.value).toBe("my answer");
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[2]![1]).toEqual(first);
  wrapper.unmount();
});

it("recovers a committed answer after a lost response without an extra save", async () => {
  vi.mocked(studyCommand).mockRejectedValueOnce(new Error("lost response")).mockResolvedValueOnce({ attempts: [saved] });
  const wrapper = render();
  await wrapper.find("textarea").setValue("my answer");
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.emitted("saved")).toEqual([[saved]]);
  expect(wrapper.text()).toContain("已保存第 1 版");
  expect(studyCommand).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("keeps local edits on conflict and requires another explicit save against the newer version", async () => {
  vi.mocked(studyCommand).mockRejectedValueOnce(new Error("conflict")).mockResolvedValueOnce({ attempts: [{ ...saved, answer_text: "another tab" }] }).mockResolvedValue({ attempt: { ...saved, version: 2, answer_text: "local edit" } });
  const wrapper = render();
  await wrapper.find("textarea").setValue("local edit");
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.find("textarea").element.value).toBe("local edit");
  expect(wrapper.text()).toContain("核对修改记录后再保存");
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[2]![1]).toMatchObject({ expected_version: 1, answer_text: "local edit" });
  wrapper.unmount();
});

it("ignores a save response after switching artifacts", async () => {
  let resolve!: (response: StudyResponse) => void;
  vi.mocked(studyCommand).mockImplementation(() => new Promise(r => { resolve = r; }));
  const wrapper = render();
  await wrapper.find("textarea").setValue("my answer");
  await wrapper.find("button").trigger("click");
  await wrapper.setProps({ artifactId: "new-artifact" });
  resolve({ attempt: saved }); await flushPromises();
  expect(wrapper.find("textarea").element.value).toBe("");
  expect(wrapper.emitted("saved")).toBeUndefined();
  wrapper.unmount();
});

it("loads paginated history without replacing a draft", async () => {
  vi.mocked(studyCommand).mockResolvedValueOnce({ attempts: [saved], next_before_version: 1 }).mockResolvedValueOnce({ attempts: [], next_before_version: null });
  const wrapper = render(saved);
  await wrapper.find("textarea").setValue("draft");
  await wrapper.findAll("button").find(b => b.text() === "修改记录")!.trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("my answer");
  await wrapper.findAll("button").find(b => b.text() === "更早的修改")!.trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[1]![1]).toMatchObject({ operation: "ATTEMPT_HISTORY", before_version: 1 });
  expect(wrapper.find("textarea").element.value).toBe("draft");
  wrapper.unmount();
});
