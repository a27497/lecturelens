import type { PracticeResult, StudyFeedbackRun } from '../../api/study';

export interface PracticeContinuation {
  index: number;
  label: string;
  reason: string;
  feedback?: StudyFeedbackRun;
}

// These are saved-work suggestions, never correctness or mastery decisions.
export function practiceContinuation(rows: PracticeResult[]): PracticeContinuation | null {
  const ordered = [...rows].sort((a, b) => a.question_index - b.question_index);
  for (const row of ordered) {
    const feedback = row.feedback_run?.feedback;
    if (!row.attempt || !feedback || row.feedback_run!.attempt_id !== row.attempt.attempt_id) continue;
    if (!feedback.note || feedback.note.disposition === 'disputed') {
      const insufficient = feedback.content.kind === 'insufficient_evidence';
      return { index: row.question_index, label: `继续核对第 ${row.question_index + 1} 题`, feedback: row.feedback_run!,
        reason: feedback.note ? '你记录了反馈异议，可回看来源与作答，再决定是否订正。' : insufficient ? '反馈提示课程证据不足。请核查来源与限制，勿据此判断答案对错。' : `第 ${row.attempt.version} 版反馈尚无核对记录。请先查证来源，再决定是否订正。` };
    }
  }
  for (const row of ordered) {
    if (!row.attempt) continue;
    const n = row.question_index + 1;
    if (['queued', 'running', 'awaiting_approval'].includes(row.latest_feedback_status ?? '')) {
      return { index: row.question_index, label: `查看第 ${n} 题反馈进度`, reason: `第 ${row.latest_feedback_answer_version ?? row.attempt.version} 版反馈尚未完成；可查看进度或已有反馈。` };
    }
    if (row.feedback_run?.feedback && row.feedback_run.attempt_id !== row.attempt.attempt_id) {
      return { index: row.question_index, label: `继续第 ${n} 题订正`, feedback: row.feedback_run,
        reason: `已保存第 ${row.attempt.version} 版作答；已有反馈仅对应第 ${row.feedback_run.answer_version} 版。请对照来源自查，新版尚无对应反馈。` };
    }
    if (!row.feedback_run?.feedback) return { index: row.question_index, label: `继续第 ${n} 题自查`, reason: '作答已保存，尚无可用反馈。可以先核对课程来源；获取反馈需另行点击。' };
  }
  const revision = ordered.find(row => row.feedback_run?.feedback?.content.observations?.some(item => item.action === 'revise' || item.action === 'clarify'));
  if (revision) return { index: revision.question_index, label: `回看第 ${revision.question_index + 1} 题订正建议`, feedback: revision.feedback_run!, reason: '你已记录核对意见，反馈仍有订正或澄清建议。可对照来源决定是否保存新版作答；核对记录不表示已订正。' };
  const unanswered = ordered.find(row => !row.attempt);
  return unanswered ? { index: unanswered.question_index, label: `继续第 ${unanswered.question_index + 1} 题作答`, reason: '本题尚无已保存作答。本页未保存文字会保留，刷新或离开页面会丢失。' } : null;
}
