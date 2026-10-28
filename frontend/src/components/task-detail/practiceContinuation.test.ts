import { expect, it } from 'vitest';
import { practiceContinuation, practiceContinuationPlan } from './practiceContinuation';
import type { PracticeResult, StudyFeedbackRun } from '../../api/study';
const attempt = { attempt_id: 'v2', artifact_id: 'artifact', question_index: 1, version: 2, answer_text: 'saved correction', created_at: '2026-10-26T00:00:00Z' };
const feedback: StudyFeedbackRun = { run_id: 'old-feedback', status: 'succeeded', error_code: null, attempt_id: 'v1', question_index: 1, answer_version: 1, feedback: { feedback_id: 'f', attempt_id: 'v1', question_index: 1, answer_version: 1, answer_text: 'old claim', note: null, content: { kind: 'insufficient_evidence', mode: 'mock', reason: 'no individual prediction data', citations: [] } } };
it('does not label old insufficient feedback as a decision about the latest answer', () => {
  const next = practiceContinuation([{ question_index: 1, attempt, feedback_run: feedback, latest_feedback_status: 'succeeded' }]);
  expect(next?.reason).toContain('已保存第 2 版'); expect(next?.reason).toContain('仅对应第 1 版');
  expect(next?.reason).not.toContain('反馈提示课程证据不足');
});
it('retains evidence-insufficient guidance for its matching answer without asserting correctness', () => {
  const next = practiceContinuation([{ question_index: 1, attempt: { ...attempt, attempt_id: 'v1', version: 1 }, feedback_run: feedback, latest_feedback_status: 'succeeded' }]);
  expect(next?.reason).toContain('勿据此判断答案对错'); expect(next?.feedback?.run_id).toBe('old-feedback');
});
it('keeps an active newer feedback distinct from the older completed feedback', () => {
  const next = practiceContinuation([{ question_index: 1, attempt, feedback_run: feedback, latest_feedback_status: 'running', latest_feedback_answer_version: 2 }]);
  expect(next?.reason).toContain('第 2 版反馈尚未完成'); expect(next?.feedback).toBeUndefined();
});
it.each(['queued', 'running', 'awaiting_approval'] as const)('opens the actual %s Run instead of an older completed feedback', status => {
  const active: StudyFeedbackRun = { ...feedback, run_id: 'active-feedback', attempt_id: attempt.attempt_id, answer_version: attempt.version, status, feedback: null };
  const rows: PracticeResult[] = [{ question_index: 1, attempt, feedback_run: feedback, latest_feedback_status: status, latest_feedback_answer_version: 2 }];
  const wrongQuestion = { ...active, run_id: 'other-question', question_index: 0 };
  const wrongVersion = { ...active, run_id: 'old-version', answer_version: 1 };
  const next = practiceContinuation(rows, [wrongQuestion, wrongVersion, active, feedback]);
  expect(next?.label).toBe('查看第 2 题反馈进度');
  expect(next?.feedback).toBe(active);
});
it('offers unsaved questions and does not treat acknowledged feedback as a grade', () => {
  const rows: PracticeResult[] = [{ question_index: 0, attempt: null, feedback_run: null, latest_feedback_status: null }];
  expect(practiceContinuation(rows)?.label).toBe('继续第 1 题作答');
  const acknowledged = { ...feedback, attempt_id: attempt.attempt_id, answer_version: 2, feedback: { ...feedback.feedback!, attempt_id: attempt.attempt_id, answer_version: 2, note: { note_id: 'n', version: 1, disposition: 'acknowledged' as const, note_text: 'checked only', created_at: attempt.created_at } } };
  expect(practiceContinuation([{ question_index: 1, attempt, feedback_run: acknowledged, latest_feedback_status: 'succeeded' }])).toBeNull();
});

function checkedRow(index: number, action: 'revise' | 'clarify' | 'retain' = 'revise'): PracticeResult {
  const saved = { ...attempt, question_index: index, attempt_id: `answer-${index}` };
  const checked: StudyFeedbackRun = { ...feedback, question_index: index, attempt_id: saved.attempt_id, answer_version: saved.version,
    feedback: { ...feedback.feedback!, question_index: index, attempt_id: saved.attempt_id, answer_version: saved.version,
      note: { note_id: `note-${index}`, version: 1, disposition: 'acknowledged', note_text: 'checked source', created_at: saved.created_at },
      content: { kind: 'guidance', mode: 'mock', citations: [], observations: [{ learner_quote: 'claim', observation: 'Check source', next_step: 'Compare claim', action, evidence_id: 'e1', evidence_quote: 'Original claim' }] } } };
  return { question_index: index, attempt: saved, feedback_run: checked, latest_feedback_status: 'succeeded' };
}

it('prioritizes unanswered work and counts checked revision suggestions in question order', () => {
  const unanswered: PracticeResult = { question_index: 2, attempt: null, feedback_run: null, latest_feedback_status: null };
  const plan = practiceContinuationPlan([checkedRow(3, 'clarify'), unanswered, checkedRow(0), checkedRow(1, 'retain')]);
  expect(plan.continuation?.index).toBe(2);
  expect(plan.continuation?.label).toBe('继续第 3 题作答');
  expect(plan.revisionHintCount).toBe(2);
  expect(plan.revisionHintIndex).toBe(0);
});

it('targets checked revision suggestions without a redundant secondary hint when only they remain', () => {
  const plan = practiceContinuationPlan([checkedRow(1, 'clarify'), checkedRow(0)]);
  expect(plan.continuation?.index).toBe(0);
  expect(plan.continuation?.label).toBe('回看第 1 题订正建议');
  expect(plan.revisionHintCount).toBe(0);
  expect(plan.revisionHintIndex).toBeNull();
});

it('has no continuation or revision hint when all saved work is checked without suggestions', () => {
  expect(practiceContinuationPlan([checkedRow(0, 'retain'), checkedRow(1, 'retain')])).toEqual({ continuation: null, revisionHintCount: 0, revisionHintIndex: null });
  expect(practiceContinuationPlan([])).toEqual({ continuation: null, revisionHintCount: 0, revisionHintIndex: null });
});

it.each(['pending', 'disputed', 'running', 'older-feedback', 'no-feedback'] as const)('shows a hint for other checked suggestions while %s work takes priority', state => {
  const primary = checkedRow(0);
  if (state === 'pending') primary.feedback_run!.feedback!.note = null;
  if (state === 'disputed') primary.feedback_run!.feedback!.note!.disposition = 'disputed';
  if (state === 'running') primary.latest_feedback_status = 'running';
  if (state === 'older-feedback') primary.attempt = { ...primary.attempt!, attempt_id: 'newer-answer', version: 3 };
  if (state === 'no-feedback') primary.feedback_run = null;
  const plan = practiceContinuationPlan([checkedRow(2), primary, checkedRow(1, 'clarify')]);
  expect(plan.continuation?.index).toBe(0);
  expect(plan.revisionHintCount).toBe(2);
  expect(plan.revisionHintIndex).toBe(1);
});
