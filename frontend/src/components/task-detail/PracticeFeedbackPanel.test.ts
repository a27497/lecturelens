import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PracticeFeedbackPanel from "./PracticeFeedbackPanel.vue";
import { studyCommand } from "../../api/study";
import type { FeedbackNote, StudyAttempt, StudyFeedback, StudyFeedbackRun, StudyResponse, StudyRun } from "../../api/study";

vi.mock("../../api/study", () => ({ studyCommand: vi.fn() }));
const attempt: StudyAttempt = { attempt_id: "answer-1", artifact_id: "artifact", question_index: 0, version: 1, answer_text: "my answer", created_at: "2026-09-20" };
const feedback: StudyFeedback = { feedback_id: "feedback", attempt_id: "answer-1", answer_version: 1, question_index: 0, answer_text: "my answer", note: null, content: { kind: "guidance", mode: "real", observations: [{ learner_quote: "my answer", observation: "Explain the stopping condition.", next_step: "Read this passage.", evidence_id: "e1", evidence_quote: "A stopping condition is required." }], citations: [{ evidence_id: "e1", text: "A stopping condition is required.", start_ms: 5000, end_ms: 6000, source_type: "SUBTITLE" }] } };
const initial: StudyFeedbackRun = { run_id: "feedback-run", status: "succeeded", error_code: null, attempt_id: "answer-1", answer_version: 1, question_index: 0, feedback };
const run: StudyRun = { run_id: "feedback-run", session_id: "session", status: "running", goal: "Feedback", model_mode: "real", model_calls: 1, tool_calls: 1, error_code: null };
const props = { taskId: "course", sessionId: "session", runId: "practice", artifactId: "artifact", questionIndex: 0, enabled: true, attempt };
const stubs = {
  "el-input": { props: ["modelValue", "disabled"], emits: ["update:modelValue"], template: `<textarea :disabled="disabled" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
};
beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers(); });
afterEach(() => vi.useRealTimers());

it("opens every supporting passage of a compound feedback observation", async () => {
  const multiple = structuredClone(feedback);
  multiple.content.observations![0]!.evidence_ids = ["e1", "e2"];
  multiple.content.citations.push({ evidence_id: "e2", text: "The second supporting passage.", start_ms: 9000, end_ms: 10000, source_type: "SUBTITLE" });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: { ...initial, feedback: multiple } }, global: { stubs } });
  await wrapper.findAll("button").find(b => b.text() === "回看课程证据 1")!.trigger("click");
  await wrapper.findAll("button").find(b => b.text() === "回看课程证据 2")!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[5000], [9000]]);
  wrapper.unmount();
});

it("requires a saved answer and an enabled feedback capability", async () => {
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, attempt: undefined }, global: { stubs } });
  expect(wrapper.find("button").attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("先保存作答");
  await wrapper.setProps({ enabled: false });
  expect(wrapper.find("button").exists()).toBe(false);
  expect(studyCommand).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("restores an active feedback run and displays the completed result after polling", async () => {
  vi.mocked(studyCommand).mockResolvedValue({ run: { ...run, status: "succeeded" }, feedback });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: { ...initial, status: "running", feedback: null } }, global: { stubs } });
  await vi.advanceTimersByTimeAsync(1500); await flushPromises();
  expect(studyCommand).toHaveBeenCalledWith("course", { operation: "READ", session_id: "session", run_id: "feedback-run" });
  expect(wrapper.text()).toContain("Explain the stopping condition.");
  await wrapper.findAll("button").find(b => b.text() === "回看这段课程证据")!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[5000]]);
  wrapper.unmount();
});

it("labels old feedback after the learner saves a newer answer", () => {
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, attempt: { ...attempt, attempt_id: "answer-2", version: 2 }, initial }, global: { stubs } });
  expect(wrapper.text()).toContain("下面反馈仅对应旧版");
  expect(wrapper.text()).toContain("第 1 版作答的证据反馈");
  wrapper.unmount();
});

it("starts feedback for the immutable answer and can cancel it", async () => {
  vi.mocked(studyCommand).mockResolvedValueOnce({ run }).mockResolvedValueOnce({ run: { ...run, status: "cancelled" } });
  const wrapper = mount(PracticeFeedbackPanel, { props, global: { stubs } });
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[0]![1]).toMatchObject({ operation: "START_FEEDBACK", attempt_id: "answer-1", artifact_id: "artifact", run_id: "practice" });
  await wrapper.findAll("button").find(b => b.text() === "取消反馈")!.trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("反馈已取消");
  await vi.advanceTimersByTimeAsync(5000);
  expect(studyCommand).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("opens saved feedback after a later cancellation and binds notes to the selected run", async () => {
  const cancelled: StudyFeedbackRun = { ...initial, run_id: "cancelled-run", status: "cancelled", feedback: null };
  vi.mocked(studyCommand).mockResolvedValueOnce({ run: { ...run, status: "succeeded" }, feedback: structuredClone(feedback) });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: cancelled, history: [cancelled, structuredClone(initial)] }, global: { stubs } });
  expect(wrapper.text()).toContain("反馈已取消");
  await wrapper.find(".feedback-history select").setValue("feedback-run"); await flushPromises();
  expect(studyCommand).toHaveBeenLastCalledWith("course", { operation: "READ", session_id: "session", run_id: "feedback-run" });
  expect(wrapper.text()).toContain("Explain the stopping condition.");
  await wrapper.find("textarea").setValue("I checked the saved feedback.");
  vi.mocked(studyCommand).mockResolvedValueOnce({ note: { note_id: "new-note", version: 1, disposition: "disputed", note_text: "I checked the saved feedback.", created_at: "2026-09-20" } });
  await wrapper.findAll("button").find(b => b.text() === "保存核对意见")!.trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.at(-1)![1]).toMatchObject({ operation: "SAVE_FEEDBACK_NOTE", run_id: "feedback-run", feedback_id: "feedback" });
  wrapper.unmount();
});

it("retains the previous result when a new feedback run is cancelled without reloading", async () => {
  const nextRun = { ...run, run_id: "next-run" };
  vi.mocked(studyCommand).mockResolvedValueOnce({ run: nextRun }).mockResolvedValueOnce({ run: { ...nextRun, status: "cancelled" } });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: structuredClone(initial) }, global: { stubs } });
  await wrapper.findAll("button").find(b => b.text() === "重新获取证据反馈")!.trigger("click"); await flushPromises();
  expect(wrapper.find(".feedback-history select").attributes("disabled")).toBeDefined();
  await wrapper.findAll("button").find(b => b.text() === "取消反馈")!.trigger("click"); await flushPromises();
  expect(wrapper.find(".feedback-history select").attributes("disabled")).toBeUndefined();
  vi.mocked(studyCommand).mockResolvedValueOnce({ run: { ...run, status: "succeeded" }, feedback });
  await wrapper.find(".feedback-history select").setValue("feedback-run"); await flushPromises();
  expect(wrapper.text()).toContain("第 1 版作答的证据反馈");
  expect(wrapper.text()).toContain("Explain the stopping condition.");
  wrapper.unmount();
});

it("saves a disputed note independently of the original model text", async () => {
  const note: FeedbackNote = { note_id: "note", version: 1, disposition: "disputed", note_text: "The feedback missed my example.", created_at: "2026-09-20" };
  vi.mocked(studyCommand).mockResolvedValue({ note });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: structuredClone(initial) }, global: { stubs } });
  await wrapper.find("textarea").setValue(note.note_text);
  await wrapper.findAll("button").find(b => b.text() === "保存核对意见")!.trigger("click"); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls[0]![1]).toMatchObject({ operation: "SAVE_FEEDBACK_NOTE", feedback_id: "feedback", expected_version: 0, disposition: "disputed", note_text: note.note_text });
  expect(wrapper.text()).toContain("你已标记反馈不准确");
  expect(wrapper.text()).toContain("Explain the stopping condition.");
  wrapper.unmount();
});

it("ignores an old course's late start response", async () => {
  let resolve!: (value: StudyResponse) => void;
  vi.mocked(studyCommand).mockImplementation(() => new Promise(r => { resolve = r; }));
  const wrapper = mount(PracticeFeedbackPanel, { props, global: { stubs } });
  await wrapper.find("button").trigger("click");
  await wrapper.setProps({ taskId: "another-course", attempt: undefined });
  resolve({ run: { ...run, status: "succeeded" }, feedback }); await flushPromises();
  expect(wrapper.text()).not.toContain("Explain the stopping condition.");
  wrapper.unmount();
});

it("stops polling when the course is deleted", async () => {
  vi.mocked(studyCommand).mockRejectedValue({ response: { status: 404 } });
  const wrapper = mount(PracticeFeedbackPanel, { props: { ...props, initial: { ...initial, status: "running", feedback: null } }, global: { stubs } });
  await vi.advanceTimersByTimeAsync(1500); await flushPromises();
  await vi.advanceTimersByTimeAsync(6000);
  expect(studyCommand).toHaveBeenCalledTimes(1);
  expect(wrapper.text()).toContain("请重新打开课程");
  wrapper.unmount();
});
