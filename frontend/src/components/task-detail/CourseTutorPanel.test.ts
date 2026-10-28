import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CourseTutorPanel from "./CourseTutorPanel.vue";
import { cancelTutorTurn, createTutorSession, getTutorSession, listTutorSessions, submitTutorTurn } from "../../api/tutor";
import type { TutorSession, TutorTurn, TutorView } from "../../api/tutor";

vi.mock("../../api/tutor", () => ({ cancelTutorTurn: vi.fn(), createTutorSession: vi.fn(), getTutorSession: vi.fn(), listTutorSessions: vi.fn(), submitTutorTurn: vi.fn() }));
const session: TutorSession = { session_id: "s1", revision: 7, status: "active", model_calls: 2, max_calls: 60 };
const turn: TutorTurn = { turn_id: "t1", client_turn_id: "key", ordinal: 1, learner_text: "Explain BFS", socratic: false,
  status: "completed", outcome: "answered", answer: "BFS explores levels [e1]", evaluation: null, error_code: null,
  citations: [{ evidence_id: "e1", text: "BFS visits one level at a time.", start_ms: 1000, end_ms: 2000, source_type: "SUBTITLE" }] };
const initial: TutorView = { session, turns: [turn] };
const wrappers: ReturnType<typeof mount>[] = [];
function open(taskId = "course") { const w = mount(CourseTutorPanel, { props: { taskId } }); wrappers.push(w); return w; }
async function click(w: ReturnType<typeof open>, text: string) {
  const button = w.findAll("button").find(b => b.text().includes(text));
  expect(button, text).toBeDefined(); await button!.trigger("click"); await flushPromises();
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [session], revision: 7 });
  vi.mocked(getTutorSession).mockResolvedValue(structuredClone(initial));
  vi.mocked(createTutorSession).mockResolvedValue({ session });
  vi.mocked(submitTutorTurn).mockResolvedValue(initial);
  vi.mocked(cancelTutorTurn).mockResolvedValue({ session, turns: [{ ...turn, status: "cancelled", outcome: "failed", answer: null, citations: [] }] });
});
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers(); });

describe("course Tutor", () => {
  it("restores history without creating sessions or model calls", async () => {
    const w = open(); await flushPromises();
    expect(w.text()).toContain("BFS explores levels");
    expect(createTutorSession).not.toHaveBeenCalled(); expect(submitTutorTurn).not.toHaveBeenCalled();
  });
  it("inline citation and source actions retain authoritative id and revision", async () => {
    const w = open(); await flushPromises(); await click(w, "[e1]");
    expect(w.emitted("seek")).toEqual([[1000, { evidenceId: "e1", revision: 7 }]]);
  });
  it("sends a follow-up with the same session and explicit Socratic toggle", async () => {
    const w = open(); await flushPromises();
    await w.find('input[type="checkbox"]').setValue(true);
    await w.find("textarea").setValue("Why is that?"); await w.find("form").trigger("submit"); await flushPromises();
    expect(submitTutorTurn).toHaveBeenCalledWith("course", "s1", expect.objectContaining({ text: "Why is that?", socratic: true }));
  });
  it("new conversation creates a session only when sending", async () => {
    const w = open(); await flushPromises(); await click(w, "新对话");
    expect(createTutorSession).not.toHaveBeenCalled();
    await w.find("textarea").setValue("Explain it"); await w.find("form").trigger("submit"); await flushPromises();
    expect(createTutorSession).toHaveBeenCalledTimes(1); expect(submitTutorTurn).toHaveBeenCalledTimes(1);
  });
  it("unknown transport result retries exact client id, text and mode", async () => {
    vi.mocked(submitTutorTurn).mockRejectedValueOnce(new Error("network"));
    const w = open(); await flushPromises(); await w.find("textarea").setValue("Why?");
    await w.find("form").trigger("submit"); await flushPromises();
    expect(w.text()).toContain("重试同一条消息"); await w.find("form").trigger("submit"); await flushPromises();
    expect(vi.mocked(submitTutorTurn).mock.calls[0]).toEqual(vi.mocked(submitTutorTurn).mock.calls[1]);
  });
  it("lost session creation uses same request key on retry", async () => {
    vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [], revision: 7 });
    vi.mocked(createTutorSession).mockRejectedValueOnce(new Error("network"));
    const w = open(); await flushPromises(); await w.find("textarea").setValue("Explain BFS");
    await w.find("form").trigger("submit"); await flushPromises();
    await w.find("form").trigger("submit"); await flushPromises();
    expect(vi.mocked(createTutorSession).mock.calls[0]).toEqual(vi.mocked(createTutorSession).mock.calls[1]);
  });
  it("insufficient evidence has explicit state without showing fabricated claims", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{ ...turn, outcome: "insufficient_evidence", answer: "I don't know from this course.", citations: [] }] });
    const w = open(); await flushPromises(); expect(w.text()).toContain("当前课程没有足够证据");
    expect(w.find(".citation").exists()).toBe(false);
  });
  it("failed turns never display any rejected candidate", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{ ...turn, status: "failed", outcome: "failed", answer: "REJECTED SECRET" }] });
    const w = open(); await flushPromises(); expect(w.text()).toContain("未发布回答"); expect(w.text()).not.toContain("REJECTED SECRET");
  });
  it("Socratic prompt and reply evaluation are visible", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{ ...turn, outcome: "socratic_prompt", answer: "What does the next level mean? [e1]", evaluation: "Compare your reasoning [e1]" }] });
    const w = open(); await flushPromises(); expect(w.text()).toContain("引导思考"); expect(w.text()).toContain("Compare your reasoning");
  });
  it("cancels an active turn and restores cancellation state", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{ ...turn, status: "running", outcome: null, answer: null }] });
    const w = open(); await flushPromises(); await click(w, "取消");
    expect(cancelTutorTurn).toHaveBeenCalledWith("course", "s1", "key"); expect(w.text()).toContain("已取消");
  });
  it("polls queued turns and restores completion", async () => {
    vi.useFakeTimers();
    vi.mocked(getTutorSession).mockResolvedValueOnce({ session, turns: [{ ...turn, status: "queued", answer: null }] }).mockResolvedValue(initial);
    const w = open(); await flushPromises(); expect(w.text()).toContain("正在查找");
    await vi.advanceTimersByTimeAsync(701); await flushPromises(); expect(w.text()).toContain("BFS explores levels");
  });
  it("late old-course history cannot replace new-course state", async () => {
    let resolve!: (value: TutorView) => void;
    vi.mocked(getTutorSession).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const w = open("old"); await flushPromises(); await w.setProps({ taskId: "new" }); await flushPromises();
    resolve({ session, turns: [{ ...turn, answer: "STALE PRIVATE" }] }); await flushPromises();
    expect(w.text()).not.toContain("STALE PRIVATE"); expect(w.text()).toContain("BFS explores levels");
  });
  it("revision or permission errors remove cached history", async () => {
    const w = open(); await flushPromises();
    vi.mocked(submitTutorTurn).mockRejectedValueOnce({ response: { status: 409 } });
    await w.find("textarea").setValue("why"); await w.find("form").trigger("submit"); await flushPromises();
    expect(w.text()).not.toContain("BFS explores levels"); expect(w.emitted("accessFailure")).toHaveLength(1);
  });
  it("exhausted session budget disables sending and permits a new conversation", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ ...initial, session: { ...session, model_calls: 60 } });
    const w = open(); await flushPromises(); expect(w.text()).toContain("预算已用完");
    expect(w.find('button[type="submit"]').attributes("disabled")).toBeDefined();
    await click(w, "新对话"); expect(w.text()).not.toContain("预算已用完");
  });
  it("renders untrusted learner and evidence text without HTML", async () => {
    vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [{ ...turn, answer: '<img src=x onerror="alert(1)"> [e1]' }] });
    const w = open(); await flushPromises(); expect(w.find("img").exists()).toBe(false); expect(w.text()).toContain("<img");
  });
  it("a late poll cannot replace a newer cancellation response", async () => {
    vi.useFakeTimers();
    const running: TutorView = { session, turns: [{ ...turn, status: "running", answer: null }] };
    let resolve!: (value: TutorView) => void;
    vi.mocked(getTutorSession).mockResolvedValueOnce(running)
      .mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const w = open(); await flushPromises();
    await vi.advanceTimersByTimeAsync(701); await flushPromises();
    await click(w, "取消"); resolve(running); await flushPromises();
    expect(w.text()).toContain("已取消"); expect(w.text()).not.toContain("正在查找");
  });
  it("a definite busy response permits refreshing the original session", async () => {
    vi.mocked(submitTutorTurn).mockRejectedValueOnce({ response: { status: 409, data: { message: "SESSION_BUSY" } } });
    const w = open(); await flushPromises();
    await w.find("textarea").setValue("why"); await w.find("form").trigger("submit"); await flushPromises();
    expect(w.text()).toContain("BFS explores levels"); expect(w.text()).not.toContain("重试同一条消息");
    expect(w.emitted("accessFailure")).toBeUndefined();
  });
});
