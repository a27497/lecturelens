import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import CourseAgentPanel from "./CourseAgentPanel.vue";
import PracticeFeedbackPanel from "./PracticeFeedbackPanel.vue";
import CourseQaPanel from "./CourseQaPanel.vue";
import { studyCommand, studyStatus } from "../../api/study";
import { askCourseQa, getEvidenceIndexStatus, readCourseQaHistory } from "../../api/qa";
import type { StudyResponse, StudyFeedbackRun, StudyAttempt } from "../../api/study";
import type { CourseQaHistoryItem } from "../../types/qa";
vi.mock("../../api/study", () => ({ studyCommand: vi.fn(), studyStatus: vi.fn(), studyEvents: vi.fn() }));
vi.mock("../../api/qa", () => ({ askCourseQa: vi.fn(), readCourseQaHistory: vi.fn(), getEvidenceIndexStatus: vi.fn(), toReadableCourseQaError: () => "failed" }));
const stubs = {
  "el-input": { props: ["modelValue", "disabled"], emits: ["update:modelValue"], template: `<textarea :disabled="disabled" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
  "el-alert": { props: ["title"], template: `<p>{{ title }}</p>` }, "el-tag": true, "el-empty": true,
  CourseModelUsagePanel: true, RouterLink: true,
};
const attempt: StudyAttempt = { attempt_id: "a1", artifact_id: "artifact", question_index: 0, version: 1, answer_text: "saved v1", created_at: "2026-10-26" };
const old: StudyFeedbackRun = { run_id: "f1", status: "succeeded", error_code: null, attempt_id: "a1", answer_version: 1, question_index: 0, feedback: { feedback_id: "feedback", attempt_id: "a1", answer_version: 1, question_index: 0, answer_text: "saved v1", note: null, content: { kind: "guidance", mode: "mock", observations: [], human_guidance: "old completed guidance", citations: [] } } };
const base: StudyResponse = { run: { run_id: "practice", session_id: "session", status: "succeeded", goal: "goal", model_mode: "mock", model_calls: 1, tool_calls: 1, error_code: null }, artifact: { artifact_id: "artifact", title: "title", explanation: "explanation", questions: [{ question: "question", evidence_ids: [] }], evidence_ids: [], citations: [], revision: 1, mode: "mock" }, attempts: [attempt], feedback_enabled: true, feedback_runs: [old] };
let server: StudyResponse;
let detail: StudyFeedbackRun;
const wrappers: ReturnType<typeof mount>[] = [];
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers(); server = structuredClone(base); detail = structuredClone(old);
  vi.mocked(studyStatus).mockResolvedValue({ enabled: true, revision: 1 });
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ status: "READY" } as never);
  vi.mocked(readCourseQaHistory).mockResolvedValue({ items: [], nextCursor: null });
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.run_id === "f1") return { run: { ...base.run!, run_id: "f1" }, feedback: structuredClone(detail.feedback) };
    if (command.run_id === "f2") return { run: { ...base.run!, run_id: "f2", status: "running" } };
    return structuredClone(server);
  });
});
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.useRealTimers(); });
async function agent() { const w = mount(CourseAgentPanel, { props: { taskId: "course" }, global: { stubs } }); wrappers.push(w); await flushPromises(); return w; }
async function click(w: ReturnType<typeof mount>, label: string) { await w.findAll("button").find(b => b.text() === label)!.trigger("click"); await flushPromises(); }
function results() { server.practice_results = [{ question_index: 0, attempt: server.attempts![0]!, feedback_run: structuredClone(detail), latest_feedback_status: server.feedback_runs![0]!.status, latest_feedback_answer_version: 2 }]; }
it("P3-R 1 refresh revalidates selected Tutor sources, including a record outside the page", async () => {
  const item: CourseQaHistoryItem = { recordId: "1", question: "old question", answer: "saved answer", status: "SUCCEEDED", createdAt: null, sourceStatus: "current", evidence: [{ sourceType: "SUBTITLE", sourceId: "1", startTimeMillis: 1, endTimeMillis: 2, snippet: "old source", translatedSnippet: "", timeText: "", confidence: null, evidenceId: "e1", revision: 1 }] };
  vi.mocked(readCourseQaHistory).mockResolvedValueOnce({ items: [item], nextCursor: null });
  const w = mount(CourseQaPanel, { props: { taskId: "course" }, global: { stubs } }); wrappers.push(w); await flushPromises();
  expect(w.find(".evidence-item").exists()).toBe(true);
  await click(w, "刷新历史");
  expect(w.find(".evidence-item").exists()).toBe(false);
  expect(w.text()).toContain("saved answer");
  expect(askCourseQa).not.toHaveBeenCalled();
});
it("P3-R 2 result opens old completed feedback while newer feedback keeps polling and can cancel", async () => {
  server.feedback_runs = [{ ...old, run_id: "f2", status: "running", feedback: null, answer_version: 2 }, old]; results();
  const w = await agent(); await click(w, "练习结果"); await click(w, "查看对应反馈");
  expect(w.get(".practice-feedback").text()).toContain("old completed guidance");
  await vi.advanceTimersByTimeAsync(1500); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.some(c => c[1].operation === "READ" && c[1].run_id === "f2")).toBe(true);
  await click(w, "取消反馈");
  expect(vi.mocked(studyCommand).mock.calls.some(c => c[1].operation === "CANCEL" && c[1].run_id === "f2")).toBe(true);
});
it("P3-R 3 reopening the same feedback reads another tab's note and preserves the local draft", async () => {
  const w = await agent(); await w.get('.practice-feedback textarea').setValue("unsaved check");
  detail.feedback!.note = { note_id: "n2", version: 2, disposition: "acknowledged", note_text: "other tab check", created_at: "2026-10-26" }; results();
  await click(w, "练习结果"); await click(w, "查看对应反馈");
  expect(w.get(".feedback-note").text()).toContain("other tab check");
  expect((w.get('.practice-feedback textarea').element as HTMLTextAreaElement).value).toBe("unsaved check");
  expect(w.get(".practice-feedback").text()).toContain("未保存");
});
it.each([false, true])("P3-R 4 result updates parent and actual form with server v2, draft=%s", async draft => {
  const w = await agent(); if (draft) await w.get('.practice-answer textarea').setValue("local draft");
  server.attempts = [{ ...attempt, attempt_id: "a2", version: 2, answer_text: "saved v2" }]; results();
  await click(w, "练习结果"); await click(w, "返回本题 / 修订");
  expect((w.get('.practice-answer textarea').element as HTMLTextAreaElement).value).toBe(draft ? "local draft" : "saved v2");
  expect(w.findComponent(PracticeFeedbackPanel).props("attempt")?.version).toBe(2);
  if (draft) expect(w.get('.practice-answer').text()).toContain("服务器");
  else expect(w.get('.practice-answer').text()).toContain("已保存第 2 版");
});

const savedQa = (id: string, status: "SUCCEEDED" | "FAILED" = "SUCCEEDED"): CourseQaHistoryItem => ({ recordId: id, question: `question ${id}`, answer: `answer ${id}`, status, createdAt: null, evidence: [], sourceStatus: "none" });
async function tutor() { const w = mount(CourseQaPanel, { props: { taskId: "course" }, global: { stubs } }); wrappers.push(w); await flushPromises(); return w; }
it("restores the most recent successful answer when the latest saved record failed", async () => {
  vi.mocked(readCourseQaHistory).mockResolvedValue({ items: [savedQa("3", "FAILED"), savedQa("2")], nextCursor: null });
  const w = await tutor(); expect(w.get(".qa-answer").text()).toContain("answer 2");
  await w.findAll(".qa-history li button")[0]!.trigger("click");
  expect(w.get(".qa-answer").text()).toContain("未形成已保存的回答");
  expect(askCourseQa).not.toHaveBeenCalled();
});
it("new question completion supersedes an in-flight history page without losing the saved answer", async () => {
  let resolvePage!: (page: Awaited<ReturnType<typeof readCourseQaHistory>>) => void;
  vi.mocked(readCourseQaHistory).mockResolvedValueOnce({ items: [savedQa("2")], nextCursor: "2" });
  const w = await tutor();
  vi.mocked(readCourseQaHistory).mockImplementationOnce(() => new Promise(resolve => { resolvePage = resolve; }));
  await click(w, "更早的问答");
  vi.mocked(askCourseQa).mockResolvedValue({ recordId: "3", answer: "new saved answer", evidence: [], usage: null });
  vi.mocked(readCourseQaHistory).mockResolvedValue({ items: [savedQa("3"), savedQa("2")], nextCursor: null });
  await w.get("textarea").setValue("new question"); await click(w, "提问");
  resolvePage({ items: [savedQa("1")], nextCursor: null }); await flushPromises();
  expect(w.get(".qa-answer").text()).toContain("new saved answer");
  expect(w.findAll(".qa-history li button").map(b => b.text()).join(" ")).toContain("question 3");
  expect(w.findAll(".qa-history li button").map(b => b.text()).join(" ")).not.toContain("question 1");
});
it("history refresh reconciles the learner's newer selection rather than restoring the previous record", async () => {
  vi.mocked(readCourseQaHistory).mockResolvedValueOnce({ items: [savedQa("2"), savedQa("1")], nextCursor: null });
  const w = await tutor();
  let finish!: (page: Awaited<ReturnType<typeof readCourseQaHistory>>) => void;
  vi.mocked(readCourseQaHistory).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  await click(w, "刷新历史"); await w.findAll(".qa-history li button")[1]!.trigger("click");
  finish({ items: [savedQa("2"), { ...savedQa("1"), answer: "revalidated answer 1" }], nextCursor: null }); await flushPromises();
  expect(w.get(".qa-answer").text()).toContain("revalidated answer 1");
  expect(w.get(".qa-answer").text()).not.toContain("answer 2");
});
it.each([409, 500])("history error %s clears trust and explains recovery while preserving saved answer", async status => {
  vi.mocked(readCourseQaHistory).mockResolvedValueOnce({ items: [savedQa("1")], nextCursor: null });
  const w = await tutor();
  vi.mocked(readCourseQaHistory).mockRejectedValueOnce({ response: { status } }); await click(w, "刷新历史");
  expect(w.get(".qa-answer").text()).toContain("answer 1");
  expect(w.get(".qa-history [role=alert]").text()).toContain(status === 409 ? "课程版本已变化" : "无法读取");
  expect(askCourseQa).not.toHaveBeenCalled();
});

it("a failed explicit history refresh cannot restore stale sources by reselecting its old list", async () => {
  const item = { ...savedQa("1"), sourceStatus: "current" as const, evidence: [{ sourceType: "SUBTITLE", sourceId: "1", startTimeMillis: 1, endTimeMillis: 2, snippet: "source", translatedSnippet: "", timeText: "", confidence: null, evidenceId: "e1", revision: 1 }] };
  vi.mocked(readCourseQaHistory).mockResolvedValueOnce({ items: [item], nextCursor: null });
  const w = await tutor(); expect(w.find(".evidence-item").exists()).toBe(true);
  vi.mocked(readCourseQaHistory).mockRejectedValueOnce({ response: { status: 500 } }); await click(w, "刷新历史");
  await w.get(".qa-history li button").trigger("click");
  expect(w.find(".evidence-item").exists()).toBe(false);
});
