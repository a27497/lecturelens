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
