import { flushPromises, mount } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import PracticeResultsPanel from "./PracticeResultsPanel.vue";
import { studyCommand } from "../../api/study";
import type { StudyArtifact, StudyFeedbackRun } from "../../api/study";
vi.mock("../../api/study", () => ({ studyCommand: vi.fn() }));
const artifact: StudyArtifact = { artifact_id: "a", title: "练习", questions: [{ question: "问题一", evidence_ids: ["e"] }, { question: "问题二", evidence_ids: ["e"] }], evidence_ids: ["e"], citations: [], explanation: "", revision: 3, mode: "mock" };
const stubs = { "el-button": { template: '<button><slot /></button>' } };
it("shows saved versions and stale feedback honestly and reads without generation", async () => {
  const feedback = { run_id: "f1", attempt_id: "v1", question_index: 0, answer_version: 1, status: "succeeded", error_code: null,
    feedback: { feedback_id: "f", attempt_id: "v1", answer_version: 1, question_index: 0, answer_text: "v1", note: null,
      content: { kind: "guidance", mode: "mock", citations: [{ evidence_id: "e", text: "原文", start_ms: 1200, end_ms: 2200, source_type: "SUBTITLE" }] } } } as StudyFeedbackRun;
  vi.mocked(studyCommand).mockResolvedValue({ artifact, practice_results: [
    { question_index: 0, attempt: { attempt_id: "v2", version: 2, artifact_id: "a", question_index: 0, answer_text: "saved", created_at: "" }, feedback_run: feedback, latest_feedback_status: "succeeded" },
    { question_index: 1, attempt: null, feedback_run: null, latest_feedback_status: null },
  ] });
  const wrapper = mount(PracticeResultsPanel, { props: { taskId: "c", sessionId: "s", runId: "r", artifact }, global: { stubs } });
  await flushPromises(); expect(wrapper.text()).toContain("已保存第 2 版"); expect(wrapper.text()).toContain("已有旧版反馈（第 1 版）"); expect(wrapper.text()).toContain("未作答"); expect(wrapper.text()).toContain("待核对");
  await wrapper.findAll('button').find(b => b.text() === "查看对应反馈")!.trigger('click');
  expect(wrapper.emitted("open")).toEqual([[0, "feedback", feedback]]);
  await wrapper.findAll('button').find(b => b.text().includes("查证来源"))!.trigger('click');
  expect(wrapper.emitted("seek")).toEqual([[1200, { evidenceId: "e", revision: 3 }, 0]]);
  expect(vi.mocked(studyCommand).mock.calls.every(c => c[1].operation === "READ")).toBe(true); wrapper.unmount();
});
it("clears result data on permission failure", async () => {
  vi.mocked(studyCommand).mockRejectedValue({ response: { status: 404 } });
  const wrapper = mount(PracticeResultsPanel, { props: { taskId: "c", sessionId: "s", runId: "r", artifact }, global: { stubs } });
  await flushPromises(); expect(wrapper.emitted("accessFailure")).toHaveLength(1); expect(wrapper.findAll('.result-question')).toHaveLength(0); wrapper.unmount();
});
