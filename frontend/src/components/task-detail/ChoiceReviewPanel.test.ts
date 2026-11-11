import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import { choiceReview, type ChoiceReview } from '../../api/study';
import ChoiceReviewPanel from './ChoiceReviewPanel.vue';

vi.mock('../../api/study', () => ({ choiceReview: vi.fn() }));
const props = { taskId: 'course', revision: 7, refreshKey: 0 };
const stubs = { 'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' } };
const response = (): ChoiceReview => ({ revision: 7, correct_count: 2, wrong_count: 1, next_after: null, items: [{
  session_id: 'older-session', run_id: 'run', artifact_id: 'artifact', question_index: 0,
  question: { kind: 'choice', question: 'Which statement is from this course?', evidence_ids: ['e'], options: [{ id: 'A', text: 'Selected statement' }, { id: 'B', text: 'Course statement' }] },
  attempt: { attempt_id: 'attempt', artifact_id: 'artifact', question_index: 0, version: 3, created_at: '', answer_text: 'Selected statement', selected_option_id: 'A', choice_result: { is_correct: false, correct_option_id: 'B', citations: [{ evidence_id: 'e', text: 'Course statement', start_ms: 1200, end_ms: 2200, source_type: 'SUBTITLE' }] } },
}] });
const mountPanel = () => mount(ChoiceReviewPanel, { props, global: { stubs } });
async function click(wrapper: ReturnType<typeof mountPanel>, text: string) {
  await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click'); await flushPromises();
}
beforeEach(() => { vi.resetAllMocks(); vi.mocked(choiceReview).mockResolvedValue(response()); });

it('reads saved cross-session facts only after opening, and emits traceable question and Evidence navigation', async () => {
  const w = mountPanel();
  try {
    expect(choiceReview).not.toHaveBeenCalled();
    await click(w, '答错待回看');
    expect(choiceReview).toHaveBeenCalledWith('course', 0);
    expect(w.text()).toContain('正确 2 · 错误 1');
    expect(w.text()).toContain('每题仅统计最新已提交版本');
    expect(w.text()).toContain('不是掌握程度');
    expect(w.text()).toContain('选择：A. Selected statement');
    expect(w.text()).toContain('正确选项：B. Course statement');
    await click(w, '打开原题与作答');
    expect(w.emitted('open')?.[0]).toEqual([response().items[0]]);
    await w.findAll('button').find(b => b.text().includes('回看课程原文'))!.trigger('click');
    expect(w.emitted('seek')?.[0]).toEqual([1200, { evidenceId: 'e', revision: 7 }]);
  } finally { w.unmount(); }
});

it('refreshes after a submitted correction and shows an honest empty state', async () => {
  const w = mountPanel();
  try {
    await click(w, '答错待回看');
    vi.mocked(choiceReview).mockResolvedValue({ revision: 7, correct_count: 3, wrong_count: 0, items: [], next_after: null });
    await w.setProps({ refreshKey: 1 }); await flushPromises();
    expect(w.findAll('.review-item')).toHaveLength(0);
    expect(w.text()).toContain('暂无答错待回看的选择题');
    expect(w.text()).toContain('正确 3 · 错误 0');
  } finally { w.unmount(); }
});

it('keeps empty or failed reads distinct from a successful empty result', async () => {
  vi.mocked(choiceReview).mockRejectedValue(new Error('offline'));
  const w = mountPanel();
  try {
    await click(w, '答错待回看');
    expect(w.get('[role=alert]').text()).toContain('暂时无法读取');
    expect(w.text()).not.toContain('暂无答错');
    expect(w.text()).not.toContain('已提交程序判分：');
    vi.mocked(choiceReview).mockResolvedValue(response());
    await click(w, '刷新答错记录');
    expect(w.findAll('.review-item')).toHaveLength(1);
  } finally { w.unmount(); }
});

it('does not present a mismatched revision as current course data', async () => {
  vi.mocked(choiceReview).mockResolvedValue({ ...response(), revision: 6 });
  const w = mountPanel();
  try {
    await click(w, '答错待回看');
    expect(w.findAll('.review-item')).toHaveLength(0);
    expect(w.find('[role=alert]').exists()).toBe(true);
  } finally { w.unmount(); }
});

it('ignores a previous course late response and clears its counts', async () => {
  let resolve!: (data: ChoiceReview) => void;
  vi.mocked(choiceReview).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  const w = mountPanel();
  try {
    await click(w, '答错待回看');
    vi.mocked(choiceReview).mockResolvedValue({ revision: 8, correct_count: 0, wrong_count: 0, items: [], next_after: null });
    await w.setProps({ taskId: 'new-course', revision: 8 }); await flushPromises();
    resolve(response()); await flushPromises();
    expect(w.findAll('.review-item')).toHaveLength(0);
    expect(w.text()).toContain('正确 0 · 错误 0');
    expect(w.text()).not.toContain('Selected statement');
  } finally { w.unmount(); }
});

it('replaces bounded pages and resets the cursor on refresh', async () => {
  vi.mocked(choiceReview).mockResolvedValueOnce({ ...response(), wrong_count: 21, next_after: 20 }).mockResolvedValue({ ...response(), wrong_count: 21 });
  const w = mountPanel();
  try {
    await click(w, '答错待回看');
    await click(w, '下一页答错记录');
    expect(choiceReview).toHaveBeenLastCalledWith('course', 20);
    expect(w.findAll('.review-item')).toHaveLength(1);
    await click(w, '刷新答错记录');
    expect(choiceReview).toHaveBeenLastCalledWith('course', 0);
  } finally { w.unmount(); }
});
