import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CourseModelUsagePanel from "./CourseModelUsagePanel.vue";
import { getCourseModelUsage } from "../../api/modelUsage";
import type { CourseModelUsage } from "../../api/modelUsage";
vi.mock("../../api/modelUsage", async original => ({ ...await original<object>(), getCourseModelUsage: vi.fn() }));
const fixture = (taskId = "course"): CourseModelUsage => ({
  taskId,
  current: { snapshotId: null, configVersion: 9, origin: "CURRENT", recordedAt: null, routes: [{ feature: "COURSE_QA", source: "DATABASE", model: "current-model-b" }] },
  pipeline: [{ snapshotId: "pipeline-a", configVersion: 4, origin: "ADOPTED", recordedAt: "2026-10-01", routes: [{ feature: "ASR_TRANSCRIPTION", source: "ENV", model: "pipeline-model-a" }] }],
  qa: [{ recordId: "123", invocationState: "SKIPPED_NO_EVIDENCE", callRecordId: null, provider: null, model: null, status: "SUCCEEDED", totalTokens: null, recordedAt: "2026-10-01", selection: { snapshotId: "qa-a", configVersion: 5, origin: "CREATED", recordedAt: "2026-10-01", routes: [{ feature: "COURSE_QA", source: "DATABASE", model: "historical-model-a" }] } }],
  calls: [],
});
const mountPanel = () => mount(CourseModelUsagePanel, { props: { taskId: "course" }, global: { stubs: { "el-button": { template: '<button><slot /></button>' } } } });
beforeEach(() => vi.resetAllMocks());

it("loads only on request and keeps current selection, historical selection and dispatch facts separate", async () => {
  vi.mocked(getCourseModelUsage).mockResolvedValue(fixture());
  const wrapper = mountPanel();
  expect(getCourseModelUsage).not.toHaveBeenCalled();
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("当前下次配置（不是历史执行记录）");
  expect(wrapper.text()).toContain("current-model-b");
  expect(wrapper.text()).toContain("historical-model-a");
  expect(wrapper.text()).toContain("接管时冻结（非创建时）");
  expect(wrapper.text()).toContain("跳过调用：证据不足");
  expect(wrapper.text()).toContain("Token：未知");
  expect(wrapper.text()).toContain("多轮工具兼容：未验证");
  expect(wrapper.text()).toContain("真实课程质量：未验证");
  expect(wrapper.findAll("a")).toHaveLength(0);
  wrapper.unmount();
});

it("discards a late response after course switch even if the transport ignores cancellation", async () => {
  let finish!: (result: CourseModelUsage) => void;
  vi.mocked(getCourseModelUsage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const wrapper = mountPanel(); await wrapper.get("button").trigger("click");
  const signal = vi.mocked(getCourseModelUsage).mock.calls[0]![1];
  await wrapper.setProps({ taskId: "other-course" });
  expect(signal?.aborted).toBe(true);
  finish(fixture()); await flushPromises();
  expect(wrapper.text()).not.toContain("historical-model-a");
  expect(wrapper.find("h3").exists()).toBe(false);
  wrapper.unmount();
});

it("clears all recorded facts on permission revocation and rejects mismatched course identity", async () => {
  vi.mocked(getCourseModelUsage).mockResolvedValueOnce(fixture()).mockRejectedValueOnce(Error("404"))
    .mockResolvedValueOnce(fixture("foreign"));
  const wrapper = mountPanel(); await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("historical-model-a");
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).not.toContain("historical-model-a");
  expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).not.toContain("historical-model-a");
  expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  wrapper.unmount();
});

it("a later refresh wins over an earlier configuration response", async () => {
  let finish!: (result: CourseModelUsage) => void;
  vi.mocked(getCourseModelUsage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce({ ...fixture(), current: null });
  const wrapper = mountPanel(); await wrapper.get("button").trigger("click");
  await wrapper.setProps({ refreshKey: "new-qa-record" }); await flushPromises();
  finish(fixture()); await flushPromises();
  expect(wrapper.text()).not.toContain("current-model-b");
  expect(wrapper.text()).toContain("未记录或系统模型管理未启用");
  wrapper.unmount();
});
