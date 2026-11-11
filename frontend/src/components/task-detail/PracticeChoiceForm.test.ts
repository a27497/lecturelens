import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import PracticeChoiceForm from './PracticeChoiceForm.vue';
import { studyCommand } from '../../api/study';
import type { StudyAttempt } from '../../api/study';
vi.mock('../../api/study', () => ({ studyCommand: vi.fn() }));
const question = { kind: 'choice' as const, question: 'Which course claim is supported?', evidence_ids: ['e1'], options: [{ id: 'A', text: 'First claim' }, { id: 'B', text: 'Second claim' }, { id: 'C', text: 'Third claim' }] };
const props = { taskId: 'task', sessionId: 'session', runId: 'run', artifactId: 'artifact', questionIndex: 0, question, sourceRevision: 7 };
const stubs = { 'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' } };
const saved = (version = 1, is_correct = false): StudyAttempt => ({ attempt_id: `a${version}`, artifact_id: 'artifact', question_index: 0, version, answer_text: version === 1 ? 'First claim' : 'Second claim', selected_option_id: version === 1 ? 'A' : 'B', created_at: '', choice_result: { is_correct, correct_option_id: 'B', citations: [{ evidence_id: 'e1', text: 'Second claim', start_ms: 1234, end_ms: 2345, source_type: 'SUBTITLE' }] } });
beforeEach(() => vi.resetAllMocks());

it('leaves an unselected question ungraded and makes no blank submission', async () => {
  const wrapper = mount(PracticeChoiceForm, { props, global: { stubs } });
  try {
    expect(wrapper.findAll('input[type=radio]')).toHaveLength(3);
    expect(wrapper.get('button').attributes('disabled')).toBeDefined();
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(studyCommand).not.toHaveBeenCalled();
    expect(wrapper.find('.choice-result').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('正确选项：');
    expect(wrapper.text()).toContain('尚未选择，未判分');
  } finally { wrapper.unmount(); }
});

it.each([true, false])('shows only the server judgment (%s) after submission, with version and evidence', async is_correct => {
  let resolve!: (value: { attempt: StudyAttempt }) => void;
  vi.mocked(studyCommand).mockImplementation(() => new Promise(r => { resolve = r; }));
  const wrapper = mount(PracticeChoiceForm, { props, global: { stubs } });
  try {
    await wrapper.get('input[value=A]').setValue();
    expect(wrapper.find('.choice-result').exists()).toBe(false);
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(studyCommand).toHaveBeenCalledWith('task', expect.objectContaining({ operation: 'SAVE_ATTEMPT', selected_option_id: 'A', expected_version: 0 }));
    const command = vi.mocked(studyCommand).mock.calls[0]![1];
    expect(command).not.toHaveProperty('answer_text'); expect(command).not.toHaveProperty('correct_option_id');
    expect(wrapper.find('.choice-result').exists()).toBe(false);
    resolve({ attempt: saved(1, is_correct) }); await flushPromises();
    expect(wrapper.get('.choice-result h4').text()).toBe(`第 1 版 · ${is_correct ? '正确' : '错误'}`);
    expect(wrapper.get('.correct-option').text()).toBe('正确选项：B. Second claim');
    await wrapper.findAll('button').find(b => b.text().includes('回看判分依据'))!.trigger('click');
    expect(wrapper.emitted('seek')).toEqual([[1234, { evidenceId: 'e1', revision: 7 }]]);
    expect(wrapper.emitted('saved')).toEqual([[saved(1, is_correct)]]);
  } finally { wrapper.unmount(); }
});

it('restores persisted results and labels the old result while a new selection is unsaved', async () => {
  const wrapper = mount(PracticeChoiceForm, { props: { ...props, attempt: saved() }, global: { stubs } });
  try {
    expect(wrapper.get('.choice-result h4').text()).toBe('第 1 版 · 错误');
    await wrapper.get('input[value=B]').setValue();
    expect(wrapper.get('.choice-result').text()).toContain('当前选择尚未提交');
    expect(wrapper.get('.choice-result h4').text()).toBe('第 1 版 · 错误');
    expect(studyCommand).not.toHaveBeenCalled();
    await wrapper.setProps({ attempt: saved(2, true) });
    expect(wrapper.get('.choice-result h4').text()).toBe('第 2 版 · 正确');
    expect(wrapper.get('.choice-result').text()).not.toContain('第 1 版');
  } finally { wrapper.unmount(); }
});

it('retries an unknown save outcome with the same key and recovers a persisted judgment', async () => {
  let attempts = 0;
  vi.mocked(studyCommand).mockImplementation(async (_task, c) => {
    if (c.operation === 'READ') return { attempts: [] };
    if (++attempts === 1) throw new Error('offline');
    return { attempt: saved() };
  });
  const wrapper = mount(PracticeChoiceForm, { props, global: { stubs } });
  try {
    await wrapper.get('input[value=A]').setValue(); await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.find('.choice-result').exists()).toBe(false);
    await wrapper.get('button').trigger('click'); await flushPromises();
    const commands = vi.mocked(studyCommand).mock.calls.filter(([, c]) => c.operation === 'SAVE_ATTEMPT').map(([, c]) => c);
    expect(commands).toHaveLength(2); expect(commands[1]).toEqual(commands[0]);
    expect(wrapper.get('.choice-result h4').text()).toBe('第 1 版 · 错误');
  } finally { wrapper.unmount(); }
});

it('does not publish an old question response after course navigation', async () => {
  let resolve!: (value: { attempt: StudyAttempt }) => void;
  vi.mocked(studyCommand).mockImplementation(() => new Promise(r => { resolve = r; }));
  const wrapper = mount(PracticeChoiceForm, { props, global: { stubs } });
  try {
    await wrapper.get('input[value=A]').setValue(); await wrapper.get('button').trigger('click'); await flushPromises();
    await wrapper.setProps({ taskId: 'new-task', artifactId: 'new-artifact', attempt: undefined });
    resolve({ attempt: saved() }); await flushPromises();
    expect(wrapper.find('.choice-result').exists()).toBe(false);
    expect(wrapper.emitted('saved')).toBeUndefined();
  } finally { wrapper.unmount(); }
});

it('keeps judgment history attached to each immutable saved version', async () => {
  vi.mocked(studyCommand).mockResolvedValue({ attempts: [saved(2, true), saved()], next_before_version: null });
  const wrapper = mount(PracticeChoiceForm, { props: { ...props, attempt: saved(2, true) }, global: { stubs } });
  try {
    await wrapper.findAll('button').find(b => b.text() === '修改记录')!.trigger('click'); await flushPromises();
    const rows = wrapper.findAll('.answer-history article');
    expect(rows[0]!.text()).toContain('第 2 版 · B · 正确');
    expect(rows[1]!.text()).toContain('第 1 版 · A · 错误');
  } finally { wrapper.unmount(); }
});
