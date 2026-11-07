/** Offline diagnosis only: asserts the current recovery deadlock without changing UI. */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import CourseTutorPanel from "../../src/components/task-detail/CourseTutorPanel.vue";
import { getTutorSession, listTutorSessions, submitTutorTurn } from "../../src/api/tutor";
import type { TutorView } from "../../src/api/tutor";

vi.mock("../../src/api/tutor", () => ({
  cancelTutorTurn: vi.fn(), createTutorSession: vi.fn(), getTutorSession: vi.fn(),
  listTutorSessions: vi.fn(), submitTutorTurn: vi.fn(),
}));
const wrappers: ReturnType<typeof mount>[] = [];
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.resetAllMocks(); });

it("lost submit response followed by exhausted restored session blocks retry and new conversation", async () => {
  const view: TutorView = {
    session: { session_id: "audit-session", revision: 1, status: "active", model_calls: 58, max_calls: 60 },
    turns: [],
  };
  vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [view.session], revision: 1 });
  vi.mocked(getTutorSession).mockResolvedValueOnce(structuredClone(view));
  vi.mocked(submitTutorTurn).mockRejectedValueOnce(new Error("synthetic lost response"));
  const w = mount(CourseTutorPanel, { props: { taskId: "audit-course" } });
  wrappers.push(w);
  await flushPromises();
  await w.find("textarea").setValue("Explain the loop");
  await w.find("form").trigger("submit");
  await flushPromises();
  const submitted = vi.mocked(submitTutorTurn).mock.calls[0]![2];
  const completed: TutorView = {
    session: { ...view.session, model_calls: 60 },
    turns: [{ turn_id: "audit-turn", client_turn_id: submitted.client_turn_id, ordinal: 1,
      learner_text: submitted.text, socratic: false, status: "completed", outcome: "answered",
      answer: "A retained answer [e1]", evaluation: "", error_code: null,
      citations: [{ evidence_id: "e1", text: "Source", start_ms: 0, end_ms: 1, source_type: "SUBTITLE" }],
    }],
  };
  vi.mocked(getTutorSession).mockResolvedValue(completed);
  const refresh = w.findAll("button").find(b => b.text() === "重新读取")!;
  await refresh.trigger("click");
  await flushPromises();
  expect(w.text()).toContain("A retained answer");
  expect(w.text()).toContain("预算已用完");
  expect(w.find('button[type="submit"]').text()).toContain("重试同一条消息");
  expect(w.find('button[type="submit"]').attributes("disabled")).toBeDefined();
  expect(w.findAll("button").find(b => b.text() === "新对话")!.attributes("disabled")).toBeDefined();
  expect(w.find("select").attributes("disabled")).toBeDefined();
  expect(w.find("textarea").attributes("disabled")).toBeDefined();
  expect(submitTutorTurn).toHaveBeenCalledTimes(1);
});

it("unvalidated HTML stays inert and rejected text stays hidden", async () => {
  const session = { session_id: "audit-session", revision: 1, status: "active" as const, model_calls: 1, max_calls: 60 };
  vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [session], revision: 1 });
  vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{
    turn_id: "audit-turn", client_turn_id: "audit-client", ordinal: 1, learner_text: "<script>bad()</script>",
    socratic: false, status: "failed", outcome: "failed", answer: "UNPUBLISHED_DRAFT",
    evaluation: "UNPUBLISHED_EVALUATION", citations: [], error_code: "TUTOR_PROTOCOL_FAILURE",
  }] });
  const w = mount(CourseTutorPanel, { props: { taskId: "audit-course" } });
  wrappers.push(w);
  await flushPromises();
  expect(w.find("script").exists()).toBe(false);
  expect(w.text()).not.toContain("UNPUBLISHED_");
});
