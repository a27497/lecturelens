import { beforeEach, expect, it, vi } from "vitest";
import { defineComponent, onMounted, ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import TaskDetailView from "./TaskDetailView.vue";
import { fetchTaskDetail } from "../api/task";
import { fetchTaskResult } from "../api/result";
import { connectTaskEvents } from "../api/taskEvents";
import { getEvidenceIndexStatus } from "../api/qa";
import { requestTaskPlaybackToken } from "../api/media";
import { probeTaskEmbeddedSubtitles } from "../api/embeddedSubtitles";
import { fetchPublicRuntimeConfiguration } from "../api/runtimeConfiguration";

vi.mock("../api/task", () => ({ fetchTaskDetail: vi.fn(), cancelTask: vi.fn(), retryTask: vi.fn(), toReadableTaskError: vi.fn() }));
vi.mock("../api/result", () => ({ fetchTaskResult: vi.fn(), toReadableTaskResultError: () => "结果暂不可用" }));
vi.mock("../api/taskEvents", () => ({ connectTaskEvents: vi.fn(), isTaskEventAuthError: () => false, toReadableTaskEventError: () => "事件暂不可用" }));
vi.mock("../api/qa", () => ({ getEvidenceIndexStatus: vi.fn() }));
vi.mock("../api/media", () => ({ requestTaskPlaybackToken: vi.fn(), toReadablePlaybackError: () => "视频暂不可用" }));
vi.mock("../api/embeddedSubtitles", () => ({ probeTaskEmbeddedSubtitles: vi.fn(), downloadTaskEmbeddedSubtitle: vi.fn(), toReadableEmbeddedSubtitleError: () => "字幕暂不可用" }));
vi.mock("../api/runtimeConfiguration", () => ({ fetchPublicRuntimeConfiguration: vi.fn() }));
const frozen = { version: 1, kind: "segments", policy: "strict", revision: 1, evidence_ids: ["e1"] };
const Agent = defineComponent({
  props: ["taskId"], emits: ["seek", "accessFailure", "frozenScope"],
  setup(_props, { emit }) { const text = ref(""); onMounted(() => emit("frozenScope", frozen)); return { text }; },
  template: `<div class="mock-agent"><input v-model="text" aria-label="目标草稿" /><button @click="$emit('seek', 2000, { evidenceId: 'e1', revision: 1 })">回看来源</button><button @click="$emit('accessFailure')">核对权限</button></div>`,
});
const Reader = defineComponent({ props: ["visible", "view", "referenceMs"], emits: ["seek"], setup(props, { expose }) { expose({ currentView: () => props.view ?? "translated" }); return { text: ref("") }; }, template: `<div class="mock-reader"><input v-model="text" aria-label="原文筛选" /><button @click="$emit('seek', 4000)">普通时间轴定位</button></div>` });
const stubs = {
  CourseAgentPanel: Agent, CourseContentPanel: Reader, CourseVideoAside: { template: `<div>视频</div>` },
  CourseScopePicker: { props: ["frozenScope"], emits: ["update:modelValue"], template: `<div class="mock-scope"><span>{{ JSON.stringify(frozenScope) }}</span><button @click="$emit('update:modelValue', { version: 1, kind: 'course', policy: 'strict', revision: 2, evidence_ids: [] })">重新选择范围</button></div>` },
  CourseModelUsagePanel: true, CourseQaPanel: true, CourseStudyPanel: true, CourseFilesPanel: true, CourseTechnicalPanel: true, CourseOverviewPanel: true,
  "el-button": { template: `<button><slot /></button>` }, "el-tag": { template: `<span><slot /></span>` }, "el-alert": { props: ["title"], template: `<p role="alert">{{ title }}</p>` }, "el-skeleton": true, "el-empty": true,
};
const result = (taskId: string) => ({ taskId, subtitles: [], translations: [], artifacts: [], keyframes: [], videoSegments: [], aiCallRecords: [] });
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchTaskDetail).mockImplementation(async taskId => ({ taskId } as never));
  vi.mocked(fetchTaskResult).mockImplementation(async taskId => result(taskId) as never);
  vi.mocked(connectTaskEvents).mockImplementation(async options => { options.onMessage({ event: "completed", data: { taskId: options.taskId, status: "SUCCEEDED", progressPercent: 100, currentStage: "DONE" } } as never); });
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ revision: 1, status: "READY" } as never);
  vi.mocked(requestTaskPlaybackToken).mockResolvedValue({ token: "synthetic", playbackUrl: "/synthetic.mp4", expiresAt: "2099-01-01T00:00:00Z" });
  vi.mocked(probeTaskEmbeddedSubtitles).mockResolvedValue({ status: "NOT_FOUND", tracks: [], selectedStreamIndex: null });
  vi.mocked(fetchPublicRuntimeConfiguration).mockResolvedValue({ demoMode: false } as never);
  HTMLElement.prototype.scrollIntoView = vi.fn(); HTMLElement.prototype.scrollTo = vi.fn(); window.scrollTo = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
});
async function open(path = "/tasks/one?view=agent&at=1000") {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/tasks", component: { template: "<div />" } }, { path: "/tasks/:taskId", component: { template: "<div />" } }] });
  await router.push(path); await router.isReady();
  const wrapper = mount(TaskDetailView, { attachTo: document.body, global: { plugins: [createPinia(), router], stubs } });
  await flushPromises(); return { wrapper, router };
}
it("moves the same reader between layouts and preserves the same learning instance during source review", async () => {
  const { wrapper, router } = await open();
  const goal = wrapper.get<HTMLInputElement>('.mock-agent input'); const node = goal.element;
  const filter = wrapper.get<HTMLInputElement>('.mock-reader input'); const reader = filter.element;
  await goal.setValue("PRIVATE_UNSUBMITTED_GOAL"); await filter.setValue("reading keyword");
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.get('.mock-agent input').element).toBe(node);
  expect(wrapper.get('.mock-reader input').element).toBe(reader);
  expect(wrapper.find('.evidence-reading').isVisible()).toBe(true);
  await wrapper.get('.layout-switch').trigger('click'); await flushPromises();
  expect(router.currentRoute.value.query.layout).toBe('classic');
  expect(wrapper.get('.mock-agent input').element).toBe(node); expect(goal.element.value).toBe('PRIVATE_UNSUBMITTED_GOAL');
  expect(wrapper.get('.mock-reader input').element).toBe(reader); expect(filter.element.value).toBe('reading keyword');
  expect(JSON.stringify(router.currentRoute.value.query)).not.toContain('PRIVATE_UNSUBMITTED_GOAL');
  wrapper.unmount();
});
it("the content URL keeps the current learning panel and its frozen scope independent of the next selection", async () => {
  const { wrapper, router } = await open();
  const input = wrapper.get<HTMLInputElement>('.mock-agent input'); await input.setValue('same-page draft');
  await wrapper.get('.mock-scope button').trigger('click');
  await wrapper.findAll('.workspace-nav button').find(b => b.text() === '课程材料')!.trigger('click'); await flushPromises();
  expect(router.currentRoute.value.query.view).toBe('content');
  expect(wrapper.get('.mock-agent input').element).toBe(input.element); expect(input.element.value).toBe('same-page draft');
  expect(wrapper.get('.mock-scope span').text()).toContain('e1'); expect(wrapper.get('.mock-scope span').text()).toContain('"revision":1');
  wrapper.unmount();
});
it.each([401,403,404])("clears cached panels after the owning course recheck confirms %s", async status => {
  const { wrapper } = await open(); await wrapper.get('.mock-agent input').setValue('private draft');
  vi.mocked(fetchTaskDetail).mockRejectedValue({ response: { status } });
  await wrapper.findAll('.mock-agent button')[1]!.trigger('click'); await flushPromises();
  expect(wrapper.get('.course-unavailable').text()).toContain('课程不可用或权限已变化');
  expect(wrapper.find('.mock-agent').exists()).toBe(false); expect(wrapper.find('.mock-reader').exists()).toBe(false);
  wrapper.unmount();
});
it("does not clear the course for a subordinate record error when the owning course is still accessible", async () => {
  const { wrapper } = await open(); const input = wrapper.get<HTMLInputElement>('.mock-agent input'); await input.setValue('retained draft');
  await wrapper.findAll('.mock-agent button')[1]!.trigger('click'); await flushPromises();
  expect(wrapper.find('.course-unavailable').exists()).toBe(false); expect(input.element.value).toBe('retained draft');
  wrapper.unmount();
});
it("ignores the old course's late denial and remounts drafts only for the new course", async () => {
  const { wrapper, router } = await open(); await wrapper.get('.mock-agent input').setValue('old private draft');
  let deny!: (reason: unknown) => void;
  vi.mocked(fetchTaskDetail).mockImplementationOnce(() => new Promise((_resolve, reject) => { deny=reject; }));
  await wrapper.findAll('.mock-agent button')[1]!.trigger('click'); await flushPromises();
  await router.push('/tasks/two?view=agent'); await flushPromises(); deny({ response: { status: 404 } }); await flushPromises();
  expect(wrapper.find('.course-unavailable').exists()).toBe(false); expect(wrapper.get<HTMLInputElement>('.mock-agent input').element.value).toBe('');
  wrapper.unmount();
});
it("hides an unverified source while preserving the task and never applies a stale revision", async () => {
  const { wrapper } = await open(); await wrapper.get('.mock-agent input').setValue('keep task draft');
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ revision: 2, status: 'READY' } as never);
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.find('.evidence-reading').isVisible()).toBe(false); expect(wrapper.get<HTMLInputElement>('.mock-agent input').element.value).toBe('keep task draft');
  expect(wrapper.text()).toContain('课程资料已更新');
  wrapper.unmount();
});

it("stops hidden narrow-screen following and resumes only when the reader is shown", async () => {
  let change!: () => void;
  const query = { matches: true, addEventListener: vi.fn((_event, listener) => { change = listener; }), removeEventListener: vi.fn() };
  vi.mocked(window.matchMedia).mockReturnValue(query as unknown as MediaQueryList);
  const { wrapper } = await open();
  expect(wrapper.findComponent(Reader).props("visible")).toBe(false);
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props("visible")).toBe(true);
  await wrapper.findAll('button').find(b => b.text() === '返回当前学习任务')!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props("visible")).toBe(false);
  query.matches = false; change(); await flushPromises();
  expect(wrapper.findComponent(Reader).props("visible")).toBe(true);
  wrapper.unmount(); expect(query.removeEventListener).toHaveBeenCalledWith("change", change);
});

it.each([
  ["/tasks/one?view=content", "timeline"],
  ["/tasks/one?view=content&layout=classic", "translated"],
])("retains the resolved reader view when toggling layout from %s", async (path, view) => {
  const { wrapper, router } = await open(path);
  const reader = wrapper.get('.mock-reader input').element;
  await wrapper.get('.layout-switch').trigger('click'); await flushPromises();
  expect(router.currentRoute.value.query.text).toBe(view);
  expect(wrapper.findComponent(Reader).props('view')).toBe(view);
  expect(wrapper.get('.mock-reader input').element).toBe(reader);
  await router.back(); await flushPromises();
  expect(wrapper.get('.mock-reader input').element).toBe(reader);
  wrapper.unmount();
});
it("returns a failed source review to the narrow task without discarding its draft", async () => {
  let change!: () => void;
  const query = { matches: false, addEventListener: vi.fn((_event, listener) => { change = listener; }), removeEventListener: vi.fn() };
  vi.mocked(window.matchMedia).mockReturnValue(query as unknown as MediaQueryList);
  const { wrapper } = await open(); await wrapper.get('.mock-agent input').setValue('retained answer');
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.get('.course-layout').classes()).toContain('is-reading');
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ revision: 2, status: 'READY' } as never);
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  query.matches = true; change(); await flushPromises();
  expect(wrapper.get('.course-layout').classes()).not.toContain('is-reading');
  expect(wrapper.get('.evidence-navigation-error').isVisible()).toBe(true);
  expect(wrapper.get('.evidence-navigation-error').element.scrollIntoView).toHaveBeenCalled();
  expect(wrapper.get<HTMLInputElement>('.mock-agent input').element.value).toBe('retained answer');
  expect(wrapper.findComponent(Reader).props('visible')).toBe(false);
  wrapper.unmount();
});

it("a rapid layout round trip supersedes its queued URL change", async () => {
  const { wrapper, router } = await open('/tasks/one?view=agent&text=timeline&at=0');
  const toggle = wrapper.get<HTMLButtonElement>('.layout-switch').element;
  toggle.click(); toggle.click(); await flushPromises();
  expect(wrapper.get('.layout-switch').text()).toBe('经典布局');
  expect(router.currentRoute.value.query.layout).toBeUndefined();
  wrapper.unmount();
});

it.each([
  ["agent", false], ["content", false], ["agent", true], ["content", true],
])("verified references from %s retain a return to learning (narrow=%s)", async (view, narrow) => {
  vi.mocked(window.matchMedia).mockReturnValue({ matches: narrow, addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList);
  const { wrapper, router } = await open(`/tasks/one?view=${view}`);
  const input = wrapper.get<HTMLInputElement>('.mock-agent input');
  await input.setValue('unsaved learning draft');
  const reader = wrapper.get('.mock-reader').element;
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBe(2000);
  expect(wrapper.findComponent(Reader).props('visible')).toBe(true);
  expect(wrapper.get('.evidence-reading__return').text()).toContain('返回当前学习任务');
  await wrapper.get('.evidence-reading__return button').trigger('click'); await flushPromises();
  expect(router.currentRoute.value.query.view).toBe('agent');
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBeUndefined();
  expect(wrapper.get('.mock-reader').element).toBe(reader);
  expect(wrapper.get('.mock-agent input').element).toBe(input.element);
  expect(input.element.value).toBe('unsaved learning draft');
  wrapper.unmount();
});

it("drops an existing verified marker before a failed recheck, without discarding the draft", async () => {
  const { wrapper } = await open();
  await wrapper.get('.mock-agent input').setValue('keep draft');
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBe(2000);
  vi.mocked(getEvidenceIndexStatus).mockResolvedValue({ revision: 2, status: 'READY' } as never);
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBeUndefined();
  expect(wrapper.findComponent(Reader).props('visible')).toBe(false);
  expect(wrapper.get<HTMLInputElement>('.mock-agent input').element.value).toBe('keep draft');
  wrapper.unmount();
});

it("ordinary timeline seeks and course changes never retain a verified marker", async () => {
  const { wrapper, router } = await open();
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBe(2000);
  await wrapper.get('.mock-reader button').trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBeUndefined();
  await wrapper.findAll('.mock-agent button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBe(2000);
  await router.push('/tasks/two?view=content'); await flushPromises();
  expect(wrapper.findComponent(Reader).props('referenceMs')).toBeUndefined();
  expect(wrapper.find('.evidence-reading__return').exists()).toBe(false);
  wrapper.unmount();
});
