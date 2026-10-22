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
const Reader = defineComponent({ setup() { return { text: ref("") }; }, template: `<div class="mock-reader"><input v-model="text" aria-label="原文筛选" /></div>` });
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
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
});
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/tasks", component: { template: "<div />" } }, { path: "/tasks/:taskId", component: { template: "<div />" } }] });
  await router.push("/tasks/one?view=agent&at=1000"); await router.isReady();
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
  await wrapper.findAll('.workspace-nav button').find(b => b.text() === '课程内容')!.trigger('click'); await flushPromises();
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
