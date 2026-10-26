import { expect, it } from 'vitest';
import { practiceContinuation } from './practiceContinuation';
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
it('offers unsaved questions and does not treat acknowledged feedback as a grade', () => {
  const rows: PracticeResult[] = [{ question_index: 0, attempt: null, feedback_run: null, latest_feedback_status: null }];
  expect(practiceContinuation(rows)?.label).toBe('继续第 1 题作答');
  const acknowledged = { ...feedback, attempt_id: attempt.attempt_id, answer_version: 2, feedback: { ...feedback.feedback!, attempt_id: attempt.attempt_id, answer_version: 2, note: { note_id: 'n', version: 1, disposition: 'acknowledged' as const, note_text: 'checked only', created_at: attempt.created_at } } };
  expect(practiceContinuation([{ question_index: 1, attempt, feedback_run: acknowledged, latest_feedback_status: 'succeeded' }])).toBeNull();
});
