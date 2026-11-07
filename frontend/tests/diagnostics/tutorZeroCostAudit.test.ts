/** Recovery regression; the original failing-state diagnosis remains at 7c913ec. */
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

it.each(["completed", "failed", "cancelled"] as const)("lost response and exhausted %s turn reconcile without another submit", async status => {
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
      learner_text: submitted.text, socratic: false, status, outcome: status === "completed" ? "answered" : "failed",
      answer: "A retained answer [e1]", evaluation: "", error_code: null,
      citations: [{ evidence_id: "e1", text: "Source", start_ms: 0, end_ms: 1, source_type: "SUBTITLE" }],
    }],
  };
  vi.mocked(getTutorSession).mockResolvedValue(completed);
  const refresh = w.findAll("button").find(b => b.text() === "重新读取")!;
  await refresh.trigger("click");
  await flushPromises();
  if (status === "completed") expect(w.text()).toContain("A retained answer");
  expect(w.text()).toContain("预算已用完");
  expect(w.find('button[type="submit"]').text()).toContain("发送");
  expect(w.find('button[type="submit"]').attributes("disabled")).toBeDefined();
  expect(w.findAll("button").find(b => b.text() === "新对话")!.attributes("disabled")).toBeUndefined();
  expect(w.find("select").attributes("disabled")).toBeUndefined();
  expect(w.find("textarea").attributes("disabled")).toBeUndefined();
  await w.findAll("button").find(b => b.text() === "新对话")!.trigger("click");
  await flushPromises();
  expect(w.text()).not.toContain("预算已用完");
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

it.each(["absent", "conflict", "forty"] as const)("exhausted read handles %s pending state without a second submit", async state => {
  const session = { session_id: "audit-session", revision: 1, status: "active" as const, model_calls: 58, max_calls: 60 };
  vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [session], revision: 1 });
  vi.mocked(getTutorSession).mockResolvedValueOnce({ session, turns: [] });
  vi.mocked(submitTutorTurn).mockRejectedValueOnce(new Error("lost"));
  const w = mount(CourseTutorPanel, { props: { taskId: "audit-course" } });
  wrappers.push(w); await flushPromises();
  await w.find("textarea").setValue("Retain this draft");
  await w.find("form").trigger("submit"); await flushPromises();
  const key = vi.mocked(submitTutorTurn).mock.calls[0]![2].client_turn_id;
  const turns: TutorView["turns"] = Array.from({ length: state === "forty" ? 40 : state === "conflict" ? 1 : 0 }, (_, index) => ({
    turn_id: `t${index}`, client_turn_id: state === "conflict" ? key : `other${index}`, ordinal: index + 1,
    learner_text: "Different saved text", socratic: false, status: "completed", outcome: "answered",
    answer: "Retained answer", evaluation: "", citations: [], error_code: null,
  }));
  vi.mocked(getTutorSession).mockResolvedValue({ session: { ...session, model_calls: state === "forty" ? 58 : 60 }, turns });
  await w.findAll("button").find(b => b.text() === "重新读取")!.trigger("click"); await flushPromises();
  expect(w.findAll("button").find(b => b.text() === "新对话")!.attributes("disabled")).toBeUndefined();
  expect(w.find("textarea").element.value).toBe("Retain this draft");
  expect(w.text()).toContain(state === "conflict" ? "冲突" : "未找到这条消息");
  expect(submitTutorTurn).toHaveBeenCalledTimes(1);
});
