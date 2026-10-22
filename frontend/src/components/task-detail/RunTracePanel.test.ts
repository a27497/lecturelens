import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import RunTracePanel from "./RunTracePanel.vue";
import { studyCommand } from "../../api/study";
import type { StudyRun } from "../../api/study";
vi.mock("../../api/study", () => ({ studyCommand: vi.fn() }));
const run: StudyRun = { run_id: "r1", session_id: "s", goal: "explain", status: "succeeded", model_mode: "real", model_calls: 2, tool_calls: 1, error_code: null };
const mountPanel = () => mount(RunTracePanel, { props: { taskId: "t", sessionId: "s", run, artifact: null }, global: { stubs: { "el-button": { template: '<button><slot /></button>' } } } });
beforeEach(() => vi.resetAllMocks());
it("loads persisted pages with non-contiguous cursors and projects only public metrics", async () => {
  vi.mocked(studyCommand).mockResolvedValueOnce({ events: Array.from({ length: 100 }, (_, i) => ({ sequence: i * 2 + 1, event_type: "model_finished", payload: { duration_ms: 17, prompt_tokens: 42, _trace: "PRIVATE" } })) }).mockResolvedValueOnce({ events: [{ sequence: 220, event_type: "run_finished", payload: { status: "succeeded" } }] });
  const wrapper = mountPanel();
  expect(studyCommand).not.toHaveBeenCalled();
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(studyCommand).toHaveBeenLastCalledWith("t", { operation: "EVENTS", session_id: "s", run_id: "r1", after: 199 });
  expect(wrapper.findAll("li")).toHaveLength(101);
  expect(wrapper.text()).toContain("prompt_tokens: 42");
  expect(wrapper.text()).not.toContain("PRIVATE");
  wrapper.unmount();
});
it("discards a late trace when the displayed run changes", async () => {
  let finish!: (value: object) => void;
  vi.mocked(studyCommand).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const wrapper = mountPanel(); await wrapper.find("button").trigger("click");
  await wrapper.setProps({ run: { ...run, run_id: "r2" } });
  finish({ events: [{ sequence: 1, event_type: "old-private-run", payload: {} }] }); await flushPromises();
  expect(wrapper.text()).not.toContain("old-private-run");
  expect(wrapper.find("h3").exists()).toBe(false); wrapper.unmount();
});
it("clears prior events if authority denies a refresh", async () => {
  vi.mocked(studyCommand).mockResolvedValueOnce({ events: [{ sequence: 1, event_type: "tool_started", payload: { tool: "search_course_evidence" } }] }).mockRejectedValueOnce(new Error("409"));
  const wrapper = mountPanel(); await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("search_course_evidence");
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  expect(wrapper.text()).not.toContain("search_course_evidence"); wrapper.unmount();
});
it("shows distinct frozen decision/review models and keeps replay and unknown usage explicit", async () => {
  vi.mocked(studyCommand).mockResolvedValue({ events: [{ sequence: 1, event_type: "model_replayed", payload: { model_selection: { model: "observed-a", version: 1, credential: "PRIVATE" }, purpose: "decision" } }] });
  const wrapper = mountPanel();
  await wrapper.setProps({ run: { ...run, model_selection: {
    decision: { connection_id: "c", name: "personal", model: "frozen-a", version: 1,
      single_turn_evidence: { ok: true, code: null, checked_at: 1700000000, version: 1 } },
    review: { connection_id: null, name: "server", model: "frozen-b", version: 0 },
  } } });
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("frozen-a"); expect(wrapper.text()).toContain("frozen-b");
  expect(wrapper.text()).toContain("个人连接"); expect(wrapper.text()).toContain("服务器默认");
  expect(wrapper.text()).toContain("2023-11-14T22:13:20.000Z");
  expect(wrapper.text()).toContain("多轮工具兼容：未验证");
  expect(wrapper.text()).toContain("重放已保存结果，非新调用");
  expect(wrapper.text()).toContain("输入 Token：未知"); expect(wrapper.text()).not.toContain("PRIVATE");
  vi.mocked(studyCommand).mockRejectedValueOnce(Error("404"));
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).not.toContain("frozen-a"); expect(wrapper.text()).not.toContain("frozen-b");
  wrapper.unmount();
});
it("does not infer an environment source when a legacy selection omits connection identity", async () => {
  vi.mocked(studyCommand).mockResolvedValue({ events: [] });
  const wrapper = mountPanel();
  await wrapper.setProps({ run: { ...run, model_selection: { decision: { name: "legacy", model: "legacy-model", version: 1 } } } });
  await wrapper.find("button").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("来源未记录");
  expect(wrapper.text()).not.toContain("服务器默认");
  wrapper.unmount();
});
