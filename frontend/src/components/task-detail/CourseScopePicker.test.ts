import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CourseScopePicker from "./CourseScopePicker.vue";
import { fetchScopeEvidence } from "../../api/learningScope";
import type { LearningScope, ScopePage } from "../../api/learningScope";
vi.mock("../../api/learningScope", async original => ({ ...await original<typeof import('../../api/learningScope')>(), fetchScopeEvidence: vi.fn() }));
const page = (revision = 1): ScopePage => ({ learningScopeVersion: 1, revision, stale: false, nextCursor: null,
  items: [{ evidenceId: `e${revision}`, revision, sourceType: "SUBTITLE", startMs: 2000, endMs: 3000, normalizedText: "Original stopping condition", retrievable: true }] });
const selected: LearningScope = { version: 1, revision: 1, kind: "segments", policy: "strict", evidence_ids: ["e1"] };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(fetchScopeEvidence).mockResolvedValue(page()); });
it("selects canonical segments with an explicit policy and reuses Evidence navigation", async () => {
  const wrapper = mount(CourseScopePicker, { props: { taskId: "task", modelValue: null } });
  await flushPromises();
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([{ version: 1, kind: 'course', policy: 'strict', revision: 1, evidence_ids: [] }]);
  await wrapper.get('input[value="segments"]').setValue(true);
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([null]);
  await wrapper.get('input[type="checkbox"]').setValue(true);
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([selected]);
  await wrapper.get('input[value="course"][type="radio"]').setValue(true);
  await wrapper.get('input[value="segments"]').setValue(true);
  const policy = wrapper.findAll('fieldset input').at(-1)!;
  await policy.setValue(true);
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([{ ...selected, policy: 'course' }]);
  await wrapper.findAll('button').find(b => b.text() === '回看')!.trigger('click');
  expect(wrapper.emitted('seek')).toEqual([[2000, { evidenceId: 'e1', revision: 1 }]]);
  wrapper.unmount();
});
it("ignores a late source page from a different course", async () => {
  let resolveOld!: (value: ScopePage) => void;
  vi.mocked(fetchScopeEvidence).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue(page(2));
  const wrapper = mount(CourseScopePicker, { props: { taskId: 'old', modelValue: null } });
  await wrapper.setProps({ taskId: 'new' }); await flushPromises();
  resolveOld(page(1)); await flushPromises();
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([{ version: 1, kind: 'course', policy: 'strict', revision: 2, evidence_ids: [] }]);
  expect(wrapper.text()).not.toContain('片段 e1'); wrapper.unmount();
});
it("invalidates a changed source revision without silently widening a selection", async () => {
  const wrapper = mount(CourseScopePicker, { props: { taskId: 'task', modelValue: selected } });
  await flushPromises();
  vi.mocked(fetchScopeEvidence).mockResolvedValue(page(2));
  await wrapper.setProps({ refreshKey: 1 }); await flushPromises();
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([null]);
  expect(wrapper.get('[role="alert"]').text()).toContain('版本已变化');
  wrapper.unmount();
});
it("keeps the restored Run scope separate from the next selection", async () => {
  const wrapper = mount(CourseScopePicker, { props: { taskId: 'task', modelValue: null, frozenScope: selected } });
  await flushPromises();
  expect(wrapper.get('.frozen-scope').text()).toContain('仅限选中范围');
  expect(wrapper.get('.frozen-scope').text()).toContain('Original stopping condition');
  expect(wrapper.props('frozenScope')).toEqual(selected);
  expect(wrapper.emitted('update:modelValue')!.at(-1)?.[0]).toMatchObject({ kind: 'course' });
  wrapper.unmount();
});
it("fails closed on source loading errors", async () => {
  vi.mocked(fetchScopeEvidence).mockRejectedValue(new Error('scope authority unavailable'));
  const wrapper = mount(CourseScopePicker, { props: { taskId: 'task', modelValue: selected } });
  await flushPromises();
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([null]);
  expect(wrapper.get('[role="alert"]').text()).toContain('unavailable'); wrapper.unmount();
});
