import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CourseAgentPanel from "./CourseAgentPanel.vue";
import PracticeFeedbackPanel from "./PracticeFeedbackPanel.vue";
import { getEvidenceIndexStatus } from "../../api/qa";
import { studyCommand, studyEvents, studyStatus } from "../../api/study";
import type { StudyArtifact, StudyRun, StudyEvent } from "../../api/study";

vi.mock("../../api/qa", () => ({ getEvidenceIndexStatus: vi.fn() }));
vi.mock("../../api/study", () => ({ studyStatus: vi.fn(), studyCommand: vi.fn(), studyEvents: vi.fn() }));
const run: StudyRun = { run_id: "run", session_id: "session", goal: "解释并出题", status: "succeeded", model_mode: "real", model_calls: 3, tool_calls: 3, error_code: null };
const artifact: StudyArtifact = { artifact_id: "artifact", title: "停止条件", explanation: "课程中描述停止条件让算法可以终止。", evidence_ids: ["e1"], questions: [{ question: "为什么需要停止条件？", evidence_ids: ["e1"] }, { question: "举一个有限执行的例子？", evidence_ids: ["e1"] }], citations: [{ evidence_id: "e1", text: "The algorithm stops.", start_ms: 1234, end_ms: 2345, source_type: "SUBTITLE" }], revision: 1, mode: "real" };
const stubs = {
  "el-input": { props: ["modelValue"], emits: ["update:modelValue"], template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />` },
  "el-button": { props: ["disabled"], template: `<button :disabled="disabled"><slot /></button>` },
  "el-alert": { props: ["title"], template: `<p role="alert">{{ title }}</p>` },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(studyCommand).mockResolvedValue({ sessions: [], runs: [] });
  vi.mocked(studyStatus).mockResolvedValue({ enabled: true, revision: 1 });
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ status: "READY" } as never);
});

it("restores a completed run, keeps answers private and preserves citation seek", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "ANSWERS") return { questions: [{ question: "why", evidence_ids: ["e1"], answer: "PRIVATE ANSWER", rubric: "matching source" }] };
    return { run, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).toContain("停止条件");
  expect(wrapper.text()).not.toContain("PRIVATE ANSWER");
  expect(vi.mocked(studyCommand).mock.calls.some(call => call[1].operation === "ANSWERS")).toBe(false);
  await wrapper.findAll("button").find(button => button.text().includes("跳到视频"))!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234, { evidenceId: "e1", revision: 1 }]]);
  await wrapper.findAll("button").find(button => button.text().includes("查看参考答案"))!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("PRIVATE ANSWER");
  wrapper.unmount();
});

it("restores an active execution and cancels it immediately", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run: { ...run, status: command.operation === "CANCEL" ? "cancelled" : "running" }, artifact: null };
  });
  vi.mocked(studyEvents).mockImplementation(() => new Promise(() => {}));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(studyEvents).toHaveBeenCalledWith("task", "session", "run", 0, expect.any(AbortSignal), expect.any(Function));
  await wrapper.findAll("button").find(button => button.text() === "取消本次执行")!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("已取消");
  expect(wrapper.findAll("button").some(button => button.text() === "取消本次执行")).toBe(false);
  wrapper.unmount();
});

it("ignores a previous course's late session response", async () => {
  let resolveOld!: (value: { sessions: { session_id: string; revision: number }[] }) => void;
  vi.mocked(studyCommand).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue({ sessions: [] });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "old" }, global: { stubs } });
  await flushPromises();
  await wrapper.setProps({ taskId: "new" });
  await flushPromises();
  resolveOld({ sessions: [{ session_id: "old-session", revision: 1 }] });
  await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.some(call => call[1].session_id === "old-session")).toBe(false);
  wrapper.unmount();
});

it("does not restore an older artifact when starting a new goal fails", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "START") throw new Error("transport unavailable");
    return { run: { ...run, request_key: "old-key" }, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.find(".study-artifact").exists()).toBe(true);
  await wrapper.get('textarea[aria-label="学习目标"]').setValue("新的学习目标");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  expect(wrapper.find(".study-artifact").exists()).toBe(false);
  wrapper.unmount();
});


it("ignores late answers from a completed run after a new run starts", async () => {
  let resolveAnswers!: (value: { questions: { question: string; evidence_ids: string[]; answer: string }[] }) => void;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "ANSWERS") return new Promise(resolve => { resolveAnswers = resolve; });
    if (command.operation === "START") return { run: { ...run, run_id: "new-run" }, artifact: { ...artifact, title: "新练习" } };
    return { run, artifact };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text().includes("查看参考答案"))!.trigger("click");
  await wrapper.get('textarea[aria-label="学习目标"]').setValue("新的学习目标");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  resolveAnswers({ questions: [{ question: "old", evidence_ids: ["e1"], answer: "OLD PRIVATE ANSWER" }] });
  await flushPromises();
  expect(wrapper.text()).toContain("新练习");
  expect(wrapper.text()).not.toContain("OLD PRIVATE ANSWER");
  wrapper.unmount();
});


it("shows insufficient evidence without empty practice or answer controls", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run, artifact: { ...artifact, kind: "insufficient_evidence", explanation: "本段课程没有涉及该主题。", questions: [], citations: [] } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).toContain("本段课程没有涉及该主题。");
  expect(wrapper.findAll("h3").some(heading => heading.text() === "两道自测题")).toBe(false);
  expect(wrapper.findAll("button").some(button => button.text().includes("查看参考答案"))).toBe(false);
  wrapper.unmount();
});

it("offers course reading when disabled without requiring the retrieval service", async () => {
  vi.mocked(studyStatus).mockResolvedValue({ enabled: false, revision: 1 });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(getEvidenceIndexStatus).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("学习助手尚未启用");
  await wrapper.findAll("button").find(button => button.text() === "阅读课程内容")!.trigger("click");
  expect(wrapper.emitted("navigate")).toEqual([["content"]]);
  wrapper.unmount();
});

it("distinguishes a status failure from disabled and allows reconnection", async () => {
  vi.mocked(studyStatus).mockRejectedValueOnce(new Error("offline"));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.text()).not.toContain("学习助手尚未启用");
  await wrapper.findAll("button").find(button => button.text() === "重新连接")!.trigger("click");
  await flushPromises();
  expect(wrapper.findAll("textarea").length).toBeGreaterThan(0);
  wrapper.unmount();
});

it("keeps learning unavailable while evidence is being prepared and can refresh", async () => {
  vi.mocked(getEvidenceIndexStatus).mockResolvedValueOnce({ status: "INDEXING" } as Awaited<ReturnType<typeof getEvidenceIndexStatus>>);
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.get('textarea[aria-label="学习目标"]').setValue("解释停止条件");
  expect(wrapper.findAll("button").find(button => button.text() === "解释并出题")!.attributes("disabled")).toBeDefined();
  await wrapper.findAll("button").find(button => button.text() === "刷新状态")!.trigger("click");
  await flushPromises();
  expect(wrapper.findAll("button").find(button => button.text() === "解释并出题")!.attributes("disabled")).toBeUndefined();
  wrapper.unmount();
});


it("shows preparation before querying the study gateway for a processing course", async () => {
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task", status: "RUNNING" }, global: { stubs } });
  await flushPromises();
  expect(studyStatus).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("课程内容尚未处理完成");
  await wrapper.find("button").trigger("click");
  expect(wrapper.emitted("navigate")).toEqual([["overview"]]);
  await wrapper.setProps({ status: "SUCCEEDED" }); await flushPromises();
  expect(studyStatus).toHaveBeenCalledWith("task");
  wrapper.unmount();
});

it("opens a saved older run from learning history", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "RUNS") return { runs: [{ run_id: "older", goal: "之前的学习目标", status: "succeeded", created_at: "2026-09-20" }] };
    return { run: { ...run, run_id: command.run_id ?? "latest" }, artifact: { ...artifact, title: command.run_id === "older" ? "以前的练习" : "当前练习" } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text() === "之前的学习目标")!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("以前的练习");
  expect(studyCommand).toHaveBeenCalledWith("task", expect.objectContaining({ operation: "READ", run_id: "older" }));
  wrapper.unmount();
});

it("restores the frozen approval choice and waiting draft after reload", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run: { ...run, status: "awaiting_approval", approval_required: true }, artifact: null,
      approval: { kind: "practice", decision: null, preview: { title: "unpublished draft", explanation: "preview only" } } };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect((wrapper.find('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true);
  expect(wrapper.text()).toContain("等待你的发布审批");
  expect(wrapper.find(".study-artifact").exists()).toBe(false);
  expect(studyEvents).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("uses the CREATE_SESSION source revision rather than the artifact edit revision", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [] };
    if (command.operation === "CREATE_SESSION") return { session_id: "session", revision: 2 };
    if (command.operation === "START") return { run, artifact };
    return {};
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  await wrapper.get("textarea").setValue("Explain the new course source");
  await wrapper.findAll("button").find(button => button.text() === "解释并出题")!.trigger("click");
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text().includes("跳到视频"))!.trigger("click");
  expect(wrapper.emitted("seek")).toEqual([[1234, { evidenceId: "e1", revision: 2 }]]);
  wrapper.unmount();
});

it("freezes the selected scope before session creation and reports the restored Run scope", async () => {
  const chosen = { version: 1 as const, kind: 'segments' as const, policy: 'strict' as const, revision: 1, evidence_ids: ['e1'] };
  let finishSession!: (value: { session_id: string; revision: number }) => void;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'CREATE_SESSION') return new Promise(resolve => { finishSession = resolve; });
    if (command.operation === 'START') return { run: { ...run, learning_scope: command.learning_scope }, artifact };
    return { sessions: [], runs: [] };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task', learningScope: chosen }, global: { stubs } });
  await flushPromises(); await wrapper.get('textarea').setValue('Selected stopping condition');
  await wrapper.findAll('button').find(b => b.text() === '解释并出题')!.trigger('click'); await flushPromises();
  await wrapper.setProps({ learningScope: { ...chosen, policy: 'course' } });
  finishSession({ session_id: 'session', revision: 1 }); await flushPromises();
  expect(vi.mocked(studyCommand).mock.calls.find(c => c[1].operation === 'START')![1].learning_scope).toEqual(chosen);
  expect(wrapper.emitted('frozenScope')!.at(-1)).toEqual([chosen]); wrapper.unmount();
});

it("keeps each question draft when navigating and only emits page navigation metadata", async () => {
  const attempt = { attempt_id: "a1", artifact_id: "artifact", question_index: 0, version: 1, answer_text: "Saved v1", created_at: "2026-10-01T00:00:00Z" };
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    return { run, artifact, attempts: [attempt] };
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  const fields = wrapper.findAll(".practice-answer textarea");
  await fields[0]!.setValue("UNSAVED question one");
  await wrapper.findAll(".question-nav button")[1]!.trigger("click");
  await fields[1]!.setValue("UNSAVED question two");
  await wrapper.findAll(".question-nav button")[0]!.trigger("click");
  expect((fields[0]!.element as HTMLTextAreaElement).value).toBe("UNSAVED question one");
  expect((fields[1]!.element as HTMLTextAreaElement).value).toBe("UNSAVED question two");
  expect(wrapper.findAll(".question-nav button")[0]!.text()).toContain("有未保存修改");
  expect(wrapper.emitted("position")!.at(-1)).toEqual([{ goal: run.goal, question: artifact.questions[0]!.question, questionIndex: 0, totalQuestions: 2, savedQuestions: 1 }]);
  expect(JSON.stringify(wrapper.emitted("position"))).not.toContain("UNSAVED");
  expect(vi.mocked(studyCommand).mock.calls.every(([, c]) => ["LIST", "READ", "RUNS"].includes(c.operation))).toBe(true);
  wrapper.unmount();
});

it("requests an ownership recheck on a current access error but ignores an old course failure", async () => {
  let rejectOld!: (reason: unknown) => void;
  vi.mocked(studyStatus).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }));
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "old" }, global: { stubs } });
  await flushPromises(); await wrapper.setProps({ taskId: "new" }); await flushPromises();
  rejectOld({ response: { status: 404 } }); await flushPromises();
  expect(wrapper.emitted("accessFailure")).toBeUndefined();
  vi.mocked(studyStatus).mockRejectedValueOnce({ response: { status: 403 } });
  await wrapper.setProps({ taskId: "revoked" }); await flushPromises();
  expect(wrapper.emitted("accessFailure")).toEqual([[]]);
  wrapper.unmount();
});

it("prioritizes the restored question over the folded new goal, and guards draft loss on history switch", async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "RUNS") return { runs: [{ ...run, created_at: "2026-10-24" }] };
    return { run, artifact };
  });
  Object.defineProperty(window, "confirm", { configurable: true, value: vi.fn(() => false) });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  expect(wrapper.get('.new-study-goal').attributes('open')).toBeUndefined();
  expect(wrapper.get('.study-artifact').element.compareDocumentPosition(wrapper.get('.new-study-goal').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const input = wrapper.get<HTMLTextAreaElement>('.practice-answer textarea');
  await input.setValue('unsaved work');
  const count = vi.mocked(studyCommand).mock.calls.length;
  await wrapper.get('.learning-history button').trigger('click'); await flushPromises();
  expect(window.confirm).toHaveBeenCalledOnce();
  expect(vi.mocked(studyCommand).mock.calls).toHaveLength(count);
  expect(wrapper.get('.practice-answer textarea').element).toBe(input.element);
  expect(input.element.value).toBe('unsaved work');
  wrapper.unmount();
});

it("clears discarded feedback-note draft markers when history reload unmounts the feedback panel", async () => {
  const state = continuationState();
  state.feedback_runs[0]!.feedback.note = null;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === "LIST") return { sessions: [{ session_id: "session", revision: 1 }] };
    if (command.operation === "RUNS") return { runs: [{ ...run, created_at: "2026-10-26" }] };
    return state;
  });
  Object.defineProperty(window, "confirm", { configurable: true, value: vi.fn(() => true) });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: "task" }, global: { stubs } });
  await flushPromises();
  const note = wrapper.get('.practice-question.is-current .practice-feedback textarea');
  await note.setValue('discarded feedback note');
  await wrapper.get('.learning-history button').trigger('click'); await flushPromises();
  expect(window.confirm).toHaveBeenCalledOnce();
  expect(wrapper.get('.practice-question.is-current .practice-feedback textarea').element).not.toBe(note.element);
  expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-feedback textarea').element.value).toBe('');
  await wrapper.get('.learning-history button').trigger('click'); await flushPromises();
  expect(window.confirm).toHaveBeenCalledOnce();
  expect(vi.mocked(studyCommand).mock.calls.every(([, command]) => ['LIST', 'RUNS', 'READ'].includes(command.operation))).toBe(true);
  wrapper.unmount();
});

function continuationState() {
  const attempts = [0, 1].map(question_index => ({ attempt_id: `a${question_index}`, artifact_id: artifact.artifact_id, question_index, version: 1, answer_text: `saved question ${question_index + 1}`, created_at: '2026-10-26T00:00:00Z' }));
  const feedback_runs = attempts.map((attempt, index) => ({ run_id: `f${index}`, status: 'succeeded' as const, error_code: null, attempt_id: attempt.attempt_id, answer_version: 1, question_index: index,
    feedback: { feedback_id: `feedback${index}`, attempt_id: attempt.attempt_id, answer_version: 1, question_index: index, answer_text: attempt.answer_text,
      content: { kind: 'guidance' as const, mode: 'mock', citations: artifact.citations, observations: [{ learner_quote: attempt.answer_text, observation: 'Check this claim against the original.', next_step: 'Inspect source, then revise.', action: 'revise' as const, evidence_id: 'e1', evidence_quote: 'The algorithm stops.' }] },
      note: index === 0 ? { note_id: 'note0', version: 1, disposition: 'acknowledged' as const, note_text: 'checked first source', created_at: attempt.created_at } : null } }));
  const practice_results = attempts.map((attempt, question_index) => ({ question_index, attempt, feedback_run: feedback_runs[question_index]!, latest_feedback_status: 'succeeded' as const, latest_feedback_answer_version: 1 }));
  return { run, artifact, attempts, feedback_runs, practice_results, feedback_enabled: true };
}

it('shows the secondary revision hint beside unanswered work and jumps to that question without losing drafts', async () => {
  const base = continuationState();
  const state = { ...base, attempts: [base.attempts[1]!],
    feedback_runs: [{ ...base.feedback_runs[1]!, feedback: { ...base.feedback_runs[1]!.feedback, note: base.feedback_runs[0]!.feedback.note } }],
    practice_results: [{ question_index: 0, attempt: null, feedback_run: null, latest_feedback_status: null },
      { ...base.practice_results[1]!, feedback_run: { ...base.feedback_runs[1]!, feedback: { ...base.feedback_runs[1]!.feedback, note: base.feedback_runs[0]!.feedback.note } } }] };
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    expect(wrapper.get('.continue-practice').text()).toBe('继续第 1 题作答');
    expect(wrapper.get('.practice-revision-hint').text()).toBe('另有 1 道题有订正建议');
    await wrapper.get('.practice-question.is-current .practice-answer textarea').setValue('local unfinished answer');
    await wrapper.get('.practice-revision-hint').trigger('click'); await flushPromises();
    expect(wrapper.get('.practice-question.is-current .question-text').text()).toContain(artifact.questions[1]!.question);
    await wrapper.findAll('.question-nav button')[0]!.trigger('click');
    expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea').element.value).toBe('local unfinished answer');
    expect(vi.mocked(studyCommand).mock.calls.every(([, command]) => ['LIST', 'READ', 'RUNS'].includes(command.operation))).toBe(true);
  } finally { wrapper.unmount(); }
});

it.each([true, false])('hides the secondary hint when checked work has revision suggestions: %s', async hasSuggestions => {
  const state = continuationState();
  state.feedback_runs[1]!.feedback.note = state.feedback_runs[0]!.feedback.note;
  if (!hasSuggestions) state.feedback_runs.forEach(row => { row.feedback.content.observations = []; });
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    expect(wrapper.find('.practice-revision-hint').exists()).toBe(false);
    expect(wrapper.find('.continue-practice').exists()).toBe(hasSuggestions);
    if (hasSuggestions) expect(wrapper.get('.continue-practice').text()).toBe('回看第 1 题订正建议');
  } finally { wrapper.unmount(); }
});

it.each(['missing-row', 'duplicate-index'] as const)('clears feedback and progress together after a malformed completion READ: %s', async malformed => {
  const initial = continuationState();
  let state = { ...initial, run: { ...run, status: 'running' as StudyRun['status'] } };
  let event!: (value: StudyEvent) => void;
  vi.mocked(studyEvents).mockImplementation((_task, _session, _run, _after, _signal, callback) => {
    event = callback;
    return new Promise(() => {});
  });
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    return structuredClone(state);
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    expect(wrapper.get('.continue-practice').text()).toBe('继续核对第 2 题');
    expect(wrapper.findAllComponents(PracticeFeedbackPanel).map(panel => panel.props('initial')?.run_id)).toEqual(['f0', 'f1']);
    state = { ...initial,
      feedback_runs: initial.feedback_runs.map(row => ({ ...row, run_id: `unvalidated-${row.run_id}` })),
      practice_results: malformed === 'missing-row' ? initial.practice_results.slice(0, 1) : [initial.practice_results[0]!, initial.practice_results[0]!] };
    event({ sequence: 1, event_type: 'run_finished', payload: {} }); await flushPromises();
    expect(wrapper.find('.continue-practice').exists()).toBe(false);
    expect(wrapper.find('.practice-revision-hint').exists()).toBe(false);
    expect(wrapper.get('.practice-continuation').text()).toContain('学习进度暂时无法读取');
    for (const panel of wrapper.findAllComponents(PracticeFeedbackPanel)) {
      expect(panel.props('initial')).toBeUndefined();
      expect(panel.props('history')).toEqual([]);
    }
    expect(wrapper.findAllComponents(PracticeFeedbackPanel)).toHaveLength(2);
    state = initial;
    await wrapper.get('.refresh-practice-progress').trigger('click'); await flushPromises();
    expect(wrapper.get('.continue-practice').text()).toBe('继续核对第 2 题');
    expect(wrapper.findAllComponents(PracticeFeedbackPanel).map(panel => panel.props('initial')?.run_id)).toEqual(['f0', 'f1']);
  } finally { wrapper.unmount(); }
});

it('continues the pending second feedback through real child panels, preserving question and note drafts without model commands', async () => {
  const state = continuationState();
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.run_id === 'f1') return { run: { ...run, run_id: 'f1' }, feedback: state.feedback_runs[1]!.feedback };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  await flushPromises();
  await wrapper.get('.practice-question.is-current .practice-answer textarea').setValue('question one local draft');
  await wrapper.get('.practice-question.is-current .practice-feedback textarea').setValue('unsaved note one');
  expect(wrapper.get('.practice-continuation').text()).toContain('第 2 题');
  await wrapper.get('.practice-continuation .continue-practice').trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-question.is-current .question-text').text()).toContain(artifact.questions[1]!.question);
  expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea').element.value).toBe('saved question 2');
  expect(wrapper.get('.practice-question.is-current .practice-feedback').text()).toContain('Check this claim');
  await wrapper.findAll('.question-nav button')[0]!.trigger('click');
  expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea').element.value).toBe('question one local draft');
  expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-feedback textarea').element.value).toBe('unsaved note one');
  expect(vi.mocked(studyCommand).mock.calls.every(([, c]) => ['LIST','READ','RUNS'].includes(c.operation))).toBe(true);
  wrapper.unmount();
});

it('refreshes continuation from another tab: keeps local draft while recognizing v2 and old v1 feedback in the actual answer form', async () => {
  let state = continuationState();
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => command.operation === 'LIST' ? { sessions: [{ session_id: 'session', revision: 1 }] } : state);
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } }); await flushPromises();
  await wrapper.findAll('.question-nav button')[1]!.trigger('click');
  const text = wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea'); await text.setValue('local correction draft');
  const second = { ...state.attempts[1]!, attempt_id: 'a1-v2', version: 2, answer_text: 'server correction v2' };
  state = { ...state, attempts: [state.attempts[0]!, second], practice_results: [state.practice_results[0]!, { ...state.practice_results[1]!, attempt: second }] };
  await wrapper.get('.practice-continuation .refresh-practice-progress').trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-continuation').text()).toContain('第 2 版');
  expect(wrapper.get('.practice-continuation').text()).toContain('第 1 版');
  expect(text.element.value).toBe('local correction draft');
  expect(wrapper.get('.practice-question.is-current .practice-answer').text()).toContain('服务器已保存第 2 版作答');
  expect(wrapper.get('.practice-question.is-current .practice-feedback').text()).toContain('下面反馈仅对应旧版');
  expect(vi.mocked(studyCommand).mock.calls.every(([, c]) => ['LIST','READ','RUNS'].includes(c.operation))).toBe(true); wrapper.unmount();
});

it.each([
  { kind: 'network', failure: new Error('network unavailable'), message: '学习进度暂时无法读取，请刷新重试；已保存记录不受影响。' },
  { kind: '409', failure: { response: { status: 409 } }, message: '课程版本或学习记录已变化，请重新打开课程核对；已保存记录不受影响。' },
])('clears feedback and continuation on a $kind progress refresh failure while preserving answer drafts', async ({ failure, message }) => {
  const state = continuationState(); let fail = false;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.operation === 'READ' && fail) throw failure;
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    expect(wrapper.get('.continue-practice').text()).toBe('继续核对第 2 题');
    expect(wrapper.findAllComponents(PracticeFeedbackPanel).map(panel => panel.props('initial')?.run_id)).toEqual(['f0', 'f1']);
    await wrapper.get('.practice-question.is-current .practice-answer textarea').setValue('keep my local answer draft');
    fail = true;
    await wrapper.get('.refresh-practice-progress').trigger('click'); await flushPromises();
    expect(wrapper.find('.continue-practice').exists()).toBe(false);
    expect(wrapper.find('.practice-revision-hint').exists()).toBe(false);
    expect(wrapper.get('.practice-continuation').text()).toContain(message);
    expect(wrapper.findAllComponents(PracticeFeedbackPanel)).toHaveLength(2);
    for (const panel of wrapper.findAllComponents(PracticeFeedbackPanel)) {
      expect(panel.props('initial')).toBeUndefined();
      expect(panel.props('history')).toEqual([]);
    }
    expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea').element.value).toBe('keep my local answer draft');
  } finally { wrapper.unmount(); }
});

it('does not navigate using a failed progress read, preserves saved content and exposes a retry', async () => {
  const state = continuationState(); let fail = false;
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.operation === 'READ' && fail) throw { response: { status: 409 } };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } }); await flushPromises();
  await wrapper.get('.practice-question.is-current .practice-answer textarea').setValue('keep my draft'); fail = true;
  await wrapper.get('.continue-practice').trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-continuation').text()).toContain('课程版本或学习记录已变化');
  expect(wrapper.find('.continue-practice').exists()).toBe(false);
  expect(wrapper.get<HTMLTextAreaElement>('.practice-question.is-current .practice-answer textarea').element.value).toBe('keep my draft');
  fail = false; await wrapper.get('.refresh-practice-progress').trigger('click'); await flushPromises();
  expect(wrapper.get('.continue-practice').text()).toContain('第 2 题'); wrapper.unmount();
});

it('fences a late continuation read after course change and does not jump when another tab changes the suggested question', async () => {
  let state = continuationState(); let delayed = false;
  let resolve!: (value: typeof state) => void;
  vi.mocked(studyCommand).mockImplementation(async (task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.operation === 'READ' && delayed && task === 'old') return new Promise(r => { resolve = r; });
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'old' }, global: { stubs } }); await flushPromises();
  delayed = true; await wrapper.get('.refresh-practice-progress').trigger('click'); await flushPromises();
  await wrapper.setProps({ taskId: 'new' }); await flushPromises();
  resolve({ ...state, practice_results: [] }); await flushPromises();
  expect(wrapper.get('.continue-practice').text()).toContain('第 2 题');
  const updated = { ...state.feedback_runs[1]!, feedback: { ...state.feedback_runs[1]!.feedback, note: { ...state.feedback_runs[0]!.feedback.note!, note_id: 'note1' } } };
  state = { ...state, practice_results: [{ ...state.practice_results[0]!, feedback_run: { ...state.feedback_runs[0]!, feedback: { ...state.feedback_runs[0]!.feedback, content: { ...state.feedback_runs[0]!.feedback.content, observations: [] } } } }, { ...state.practice_results[1]!, feedback_run: { ...updated, feedback: { ...updated.feedback, content: { ...updated.feedback.content, observations: [] } } } }] };
  await wrapper.get('.continue-practice').trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-question.is-current .question-text').text()).toContain(artifact.questions[0]!.question);
  expect(wrapper.get('.practice-continuation').text()).toContain('学习进度已更新'); wrapper.unmount();
});

it('recomputes continuation after the real child saves a check note without another run', async () => {
  let state = continuationState();
  const note = { note_id: 'new-note', version: 1, disposition: 'acknowledged' as const, note_text: 'Checked source; correction needed.', created_at: '2026-10-26T00:00:00Z' };
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.operation === 'SAVE_FEEDBACK_NOTE') {
      const row = state.practice_results[1]!;
      state = { ...state, practice_results: [state.practice_results[0]!, { ...row, feedback_run: { ...row.feedback_run, feedback: { ...row.feedback_run.feedback, note } } }] };
      return { note };
    }
    if (command.run_id === 'f1') return { run: { ...run, run_id: 'f1' }, feedback: state.feedback_runs[1]!.feedback };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } }); await flushPromises();
  await wrapper.get('.continue-practice').trigger('click'); await flushPromises();
  const panel = wrapper.get('.practice-question.is-current .practice-feedback');
  await panel.get('textarea').setValue(note.note_text); await panel.findAll('select').at(-1)!.setValue('acknowledged');
  await panel.findAll('button').find(b => b.text() === '保存核对意见')!.trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-continuation').text()).not.toContain('尚无核对记录');
  expect(wrapper.get('.practice-continuation').text()).toContain('核对记录不表示已订正');
  expect(vi.mocked(studyCommand).mock.calls.some(([, c]) => ['START', 'START_FEEDBACK', 'CREATE_SESSION'].includes(c.operation))).toBe(false); wrapper.unmount();
});

it('keeps saved progress when a late completion read arrives after the answer form saves', async () => {
  const state = continuationState();
  const empty = { ...state, attempts: [], feedback_runs: [], practice_results: state.practice_results.map(row => ({ ...row, attempt: null, feedback_run: null, latest_feedback_status: null })) };
  const saved = { ...empty, attempts: [state.attempts[0]!], practice_results: [{ ...empty.practice_results[0]!, attempt: state.attempts[0]! }, empty.practice_results[1]!] };
  let reads = 0; let finish!: () => void; let event!: (value: StudyEvent) => void;
  let late!: (value: typeof empty) => void;
  vi.mocked(studyEvents).mockImplementation((_task, _session, _run, _after, _signal, callback) => {
    event = callback; return new Promise(resolve => { finish = resolve; });
  });
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (command.operation === 'SAVE_ATTEMPT') return { attempt: state.attempts[0]! };
    if (command.operation === 'READ') {
      reads++;
      if (reads === 1) return { run: { ...run, status: 'running' }, artifact: null };
      if (reads === 2) return empty;
      if (reads === 3) return new Promise(resolve => { late = resolve; });
      return saved;
    }
    return {};
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } }); await flushPromises();
  event({ sequence: 1, event_type: 'run_finished', payload: {} }); await flushPromises(); finish(); await flushPromises();
  const form = wrapper.get('.practice-question.is-current .practice-answer'); await form.get('textarea').setValue(state.attempts[0]!.answer_text);
  await form.findAll('button').find(b => b.text() === '保存作答')!.trigger('click'); await flushPromises();
  expect(wrapper.get('.practice-continuation').text()).toContain('作答已保存');
  late(empty); await flushPromises();
  expect(wrapper.get('.practice-guidance').text()).toContain('已保存 1/2');
  expect(wrapper.get('.practice-continuation').text()).toContain('作答已保存');
  expect(form.get<HTMLTextAreaElement>('textarea').element.value).toBe(state.attempts[0]!.answer_text); wrapper.unmount();
});

it('starts choice practice only after explicit format selection and keeps open practice default', async () => {
  vi.mocked(studyCommand).mockImplementation(async (_task, command) => {
    if (command.operation === 'LIST') return { sessions: [] };
    if (command.operation === 'CREATE_SESSION') return { session_id: 'session', revision: 1 };
    if (command.operation === 'START') return { run, artifact };
    return {};
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    expect(wrapper.get('select[aria-label="练习形式"]').element).toHaveProperty('value', 'open');
    await wrapper.get('select[aria-label="练习形式"]').setValue('choice');
    expect(studyCommand).not.toHaveBeenCalledWith('task', expect.objectContaining({ operation: 'START' }));
    await wrapper.get('textarea').setValue('Identify course evidence.');
    await wrapper.findAll('button').find(b => b.text() === '解释并出题')!.trigger('click'); await flushPromises();
    expect(studyCommand).toHaveBeenCalledWith('task', expect.objectContaining({ operation: 'START', practice_format: 'choice', approval_required: false }));
  } finally { wrapper.unmount(); }
});
