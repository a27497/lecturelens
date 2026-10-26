import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CourseAgentPanel from "./CourseAgentPanel.vue";
import { getEvidenceIndexStatus } from "../../api/qa";
import { studyCommand, studyEvents, studyStatus } from "../../api/study";
import type { StudyArtifact, StudyRun, StudyEvent } from "../../api/study";

vi.mock("../../api/qa", () => ({ getEvidenceIndexStatus: vi.fn() }));
vi.mock("../../api/study", () => ({ studyStatus: vi.fn(), studyCommand: vi.fn(), studyEvents: vi.fn() }));
const run: StudyRun = { run_id: "run", session_id: "session", goal: "解释并出题", status: "succeeded", model_mode: "real", model_calls: 3, tool_calls: 3, error_code: null };
const artifact: StudyArtifact = { artifact_id: "artifact", title: "停止条件", explanation: "课程中描述停止条件让算法可以终止。", evidence_ids: ["e1"], questions: [{ question: "为什么需要停止条件？", evidence_ids: ["e1"] }, { question: "举一个有限执行的例子？", evidence_ids: ["e1"] }], citations: [{ evidence_id: "e1", text: "The algorithm stops.", start_ms: 1234, end_ms: 2345, source_type: "SUBTITLE" }], revision: 1, mode: "real" };
const stubs = {
  RouterLink: { template: '<a><slot /></a>' },
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
function continuationState() {
  const attempts = [0, 1].map(question_index => ({ attempt_id: `a${question_index}`, artifact_id: artifact.artifact_id, question_index, version: 1, answer_text: `saved question ${question_index + 1}`, created_at: '2026-10-26T00:00:00Z' }));
  const feedback_runs = attempts.map((attempt, index) => ({ run_id: `f${index}`, status: 'succeeded' as const, error_code: null, attempt_id: attempt.attempt_id, answer_version: 1, question_index: index,
    feedback: { feedback_id: `feedback${index}`, attempt_id: attempt.attempt_id, answer_version: 1, question_index: index, answer_text: attempt.answer_text,
      content: { kind: 'guidance' as const, mode: 'mock', citations: artifact.citations, observations: [{ learner_quote: attempt.answer_text, observation: 'Check this claim against the original.', next_step: 'Inspect source, then revise.', action: 'revise' as const, evidence_id: 'e1', evidence_quote: 'The algorithm stops.' }] },
      note: index === 0 ? { note_id: 'note0', version: 1, disposition: 'acknowledged' as const, note_text: 'checked first source', created_at: attempt.created_at } : null } }));
  const practice_results = attempts.map((attempt, question_index) => ({ question_index, attempt, feedback_run: feedback_runs[question_index]!, latest_feedback_status: 'succeeded' as const, latest_feedback_answer_version: 1 }));
  return { run, artifact, attempts, feedback_runs, practice_results, feedback_enabled: true };
}


it('REVIEW: refresh plus View progress must open the active feedback started in another tab', async () => {
  const initial = continuationState();
  initial.practice_results[0]!.feedback_run.feedback.content.observations = [];
  initial.feedback_runs[0]!.feedback.content.observations = [];
  let state: any = { ...initial,
    feedback_runs: [initial.feedback_runs[0]],
    practice_results: [initial.practice_results[0], { ...initial.practice_results[1], feedback_run: null, latest_feedback_status: null }] };
  vi.mocked(studyCommand).mockImplementation(async (_task, c) => {
    if (c.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (c.operation === 'READ' && c.run_id === 'cross-tab-active') return { run: { ...run, run_id: c.run_id, status: 'awaiting_approval' }, feedback: null };
    return structuredClone(state);
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises();
    const active = { run_id: 'cross-tab-active', status: 'awaiting_approval', question_index: 1, attempt_id: state.attempts[1].attempt_id, answer_version: 1, feedback: null, error_code: null };
    state = { ...state, feedback_runs: [active, ...state.feedback_runs], practice_results: [state.practice_results[0], { ...state.practice_results[1], latest_feedback_status: 'awaiting_approval', latest_feedback_answer_version: 1 }] };
    await wrapper.get('.refresh-practice-progress').trigger('click'); await flushPromises();
    expect(wrapper.get('.continue-practice').text()).toContain('查看第 2 题反馈进度');
    await wrapper.get('.continue-practice').trigger('click'); await flushPromises();
    const panel = wrapper.get('.practice-question.is-current .practice-feedback');
    expect(panel.text()).toContain('等待发布审批');
    expect(panel.findAll('button').some(b => b.text() === '取消反馈')).toBe(true);
    expect(studyCommand).toHaveBeenCalledWith('task', { operation: 'READ', session_id: 'session', run_id: 'cross-tab-active' });
  } finally { wrapper.unmount(); }
});

it.each(['succeeded', 'awaiting_approval'] as const)('REVIEW: late completion snapshot (%s) must not undo the visible saved feedback note', async lateStatus => {
  const base = continuationState();
  const note = { note_id: 'n1', version: 1, disposition: 'acknowledged' as const, note_text: 'Independent source check saved', created_at: '2026-10-26T00:00:00Z' };
  let state: any = structuredClone(base);
  let reads = 0; let finish!: () => void; let event!: (value: StudyEvent) => void; let late!: (value: any) => void;
  vi.mocked(studyEvents).mockImplementation((_task, _session, _run, _after, _signal, callback) => { event = callback; return new Promise(resolve => { finish = resolve; }); });
  vi.mocked(studyCommand).mockImplementation(async (_task, c) => {
    if (c.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (c.operation === 'SAVE_FEEDBACK_NOTE') {
      state.feedback_runs[1].feedback.note = note; state.practice_results[1].feedback_run.feedback.note = note;
      return { note: structuredClone(note) };
    }
    if (c.operation === 'READ') {
      if (c.run_id === 'f1') return { run: { ...run, run_id: 'f1' }, feedback: structuredClone(state.feedback_runs[1].feedback) };
      reads++;
      if (reads === 1) return { run: { ...run, status: 'running' }, artifact: null };
      if (reads === 2) return structuredClone(base);
      if (reads === 3) return new Promise(resolve => { late = resolve; });
      return structuredClone(state);
    }
    return {};
  });
  const wrapper = mount(CourseAgentPanel, { props: { taskId: 'task' }, global: { stubs } });
  try {
    await flushPromises(); event({ sequence: 1, event_type: 'run_finished', payload: {} }); await flushPromises(); finish(); await flushPromises();
    await wrapper.findAll('.question-nav button')[1]!.trigger('click'); await flushPromises();
    const panel = wrapper.get('.practice-question.is-current .practice-feedback');
    await panel.get('textarea').setValue(note.note_text); await panel.findAll('select').at(-1)!.setValue('acknowledged');
    await panel.findAll('button').find(b => b.text() === '保存核对意见')!.trigger('click'); await flushPromises();
    expect(panel.text()).toContain('你已核对反馈');
    const stale = structuredClone(base);
    late({ ...stale, feedback_runs: stale.feedback_runs.map(row => row.run_id === 'f1' ? { ...row, status: lateStatus, feedback: lateStatus === 'succeeded' ? row.feedback : null } : row) }); await flushPromises();
    expect(panel.text()).toContain('你已核对反馈');
    expect(panel.text()).not.toContain('等待发布审批');
  } finally { wrapper.unmount(); }
});

it('REVIEW: continue checking must target feedback after expanded answer history', async () => {
  const state = continuationState();
  state.attempts[1]!.version = 3;
  state.feedback_runs[1]!.answer_version = 3;
  state.feedback_runs[1]!.feedback.answer_version = 3;
  vi.mocked(studyCommand).mockImplementation(async (_task, c) => {
    if (c.operation === 'LIST') return { sessions: [{ session_id: 'session', revision: 1 }] };
    if (c.operation === 'ATTEMPT_HISTORY') return { attempts: [3,2,1].map(version => ({ ...state.attempts[1]!, version, attempt_id: `history-v${version}`, answer_text: 'Long saved answer line\n'.repeat(100) })), next_before_version: null };
    if (c.run_id === 'f1') return { run: { ...run, run_id: 'f1' }, feedback: state.feedback_runs[1]!.feedback };
    return state;
  });
  const wrapper = mount(CourseAgentPanel, { attachTo: document.body, props: { taskId: 'task' }, global: { stubs } });
  const targets: Element[] = [];
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(function(this: Element) { targets.push(this); });
  try {
    await flushPromises(); await wrapper.findAll('.question-nav button')[1]!.trigger('click');
    const form = wrapper.get('.practice-question.is-current .practice-answer');
    await form.findAll('button').find(b => b.text() === '修改记录')!.trigger('click'); await flushPromises();
    expect(form.findAll('.answer-history article')).toHaveLength(3);
    await wrapper.findAll('.question-nav button')[0]!.trigger('click'); targets.length = 0;
    await wrapper.get('.continue-practice').trigger('click'); await flushPromises();
    expect(targets.some(e => e.classList.contains('practice-feedback'))).toBe(true);
    expect(targets.at(-1)).toBe(wrapper.get('.practice-question.is-current .practice-feedback').element);
    expect(document.activeElement).toBe(targets.at(-1));
    expect(form.findAll('.answer-history article')).toHaveLength(3);
  } finally { wrapper.unmount(); scroll.mockRestore(); }
});
