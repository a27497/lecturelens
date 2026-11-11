import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CourseFlashcardsPanel from "./CourseFlashcardsPanel.vue";
import { dueCards, studyCommand, studyStatus } from "../../api/study";
import type { DueCards, EvidenceCard } from "../../api/study";

vi.mock("../../api/study", () => ({ dueCards: vi.fn(), studyCommand: vi.fn(), studyStatus: vi.fn() }));
const card: EvidenceCard = { card_id: "c1", deck_id: "d1", front: "What is halved?", back: "The interval.", version: 0,
  due_at: "2026-01-01T00:00:00Z", revision: 7,
  citations: [{ evidence_id: "e1", text: "Halve the interval.", start_ms: 1000, end_ms: 2000, source_type: "SUBTITLE" }] };
const initial: DueCards = { cards: [card], due_count: 1, total_count: 1, reviewed_today: 0, next_due_at: null,
  generation: null, server_now: "2026-01-01T00:00:00Z", day_timezone: "UTC" };
const wrappers: ReturnType<typeof mount>[] = [];
function open(taskId = "course") { const wrapper = mount(CourseFlashcardsPanel, { props: { taskId } }); wrappers.push(wrapper); return wrapper; }
async function click(wrapper: ReturnType<typeof open>, text: string) {
  const button = wrapper.findAll("button").find(b => b.text().includes(text));
  expect(button, text).toBeDefined(); await button!.trigger("click"); await flushPromises();
}
beforeEach(() => {
  vi.resetAllMocks(); vi.mocked(studyStatus).mockResolvedValue({ enabled: true, revision: 7 });
  vi.mocked(dueCards).mockResolvedValue(structuredClone(initial)); vi.mocked(studyCommand).mockResolvedValue({ session_id: "s1" });
});
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); });

describe("evidence flashcards", () => {
  it("opening and refreshing read saved progress without creating sessions or runs", async () => {
    const wrapper = open(); await flushPromises();
    expect(wrapper.text()).toContain("今日待复习 1"); expect(wrapper.text()).not.toContain(card.back);
    expect(studyCommand).not.toHaveBeenCalled();
    window.dispatchEvent(new Event("focus")); await flushPromises();
    expect(dueCards).toHaveBeenCalledTimes(2); expect(studyCommand).not.toHaveBeenCalled();
  });
  it("requires flipping before self rating, saves version then restores the remaining queue", async () => {
    const wrapper = open(); await flushPromises(); expect(wrapper.find('[aria-label="回忆难度自评"]').exists()).toBe(false);
    await click(wrapper, "翻面"); expect(wrapper.text()).toContain(card.back);
    vi.mocked(dueCards).mockResolvedValue({ ...initial, cards: [], due_count: 0, reviewed_today: 1, next_due_at: "2026-01-02T00:00:00Z" });
    await click(wrapper, "Good");
    expect(studyCommand).toHaveBeenCalledWith("course", expect.objectContaining({ operation: "REVIEW_CARD", card_id: "c1", expected_version: 0, rating: "Good" }));
    expect(wrapper.text()).toContain("当前复习已完成"); expect(wrapper.text()).toContain("今日已复习 1");
    wrapper.unmount(); const refreshed = open(); await flushPromises();
    expect(refreshed.text()).toContain("当前复习已完成"); expect(studyCommand).toHaveBeenCalledTimes(1);
  });
  it("source action retains canonical Evidence identity and revision", async () => {
    const wrapper = open(); await flushPromises(); await click(wrapper, "翻面"); await click(wrapper, "回看视频");
    expect(wrapper.emitted("seek")).toEqual([[1000, { evidenceId: "e1", revision: 7 }]]);
    expect(studyCommand).not.toHaveBeenCalled();
  });
  it("lost review response reuses request key and exact rating on retry", async () => {
    const wrapper = open(); await flushPromises(); await click(wrapper, "翻面");
    vi.mocked(studyCommand).mockRejectedValueOnce(new Error("network"));
    await click(wrapper, "Good"); await click(wrapper, "重试上次评分");
    const calls = vi.mocked(studyCommand).mock.calls;
    expect(calls).toHaveLength(2); expect(calls[0]).toEqual(calls[1]);
  });
  it("concurrent version conflict reloads the next card without overwriting", async () => {
    const wrapper = open(); await flushPromises(); await click(wrapper, "翻面");
    vi.mocked(studyCommand).mockRejectedValueOnce({ response: { status: 409 } });
    vi.mocked(dueCards).mockResolvedValue({ ...initial, cards: [{ ...card, card_id: "c2", front: "Next question" }] });
    await click(wrapper, "Good");
    expect(wrapper.text()).toContain("Next question"); expect(wrapper.text()).not.toContain(card.back);
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  });
  it("generation only starts on an explicit click", async () => {
    const wrapper = open(); await flushPromises(); expect(studyCommand).not.toHaveBeenCalled();
    await click(wrapper, "生成一组");
    expect(studyCommand).toHaveBeenNthCalledWith(1, "course", expect.objectContaining({ operation: "CREATE_SESSION" }));
    expect(studyCommand).toHaveBeenNthCalledWith(2, "course", expect.objectContaining({ operation: "GENERATE_CARDS", session_id: "s1" }));
  });
  it("disabled service keeps generation unavailable", async () => {
    vi.mocked(studyStatus).mockResolvedValue({ enabled: false, revision: 7 });
    const wrapper = open(); await flushPromises();
    expect(wrapper.text()).toContain("学习服务未启用"); expect(dueCards).not.toHaveBeenCalled(); expect(studyCommand).not.toHaveBeenCalled();
  });
  it("late old-course data cannot replace a newer course", async () => {
    let resolve!: (value: DueCards) => void;
    vi.mocked(dueCards).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const wrapper = open("old"); await flushPromises();
    await wrapper.setProps({ taskId: "new" }); await flushPromises();
    resolve({ ...initial, cards: [{ ...card, front: "STALE PRIVATE" }] }); await flushPromises();
    expect(wrapper.text()).not.toContain("STALE PRIVATE"); expect(wrapper.text()).toContain(card.front);
  });
  it("revoked access removes cached cards", async () => {
    const wrapper = open(); await flushPromises();
    vi.mocked(dueCards).mockRejectedValueOnce({ response: { status: 404 } });
    window.dispatchEvent(new Event("focus")); await flushPromises();
    expect(wrapper.text()).not.toContain(card.front); expect(wrapper.emitted("accessFailure")).toHaveLength(1);
  });
  it("restores and cancels an in-progress generation", async () => {
    const run = { run_id: "run", session_id: "session", status: "running", model_mode: "mock", model_calls: 1,
      tool_calls: 1, goal: "cards", error_code: null } as const;
    vi.mocked(dueCards).mockResolvedValue({ ...initial, generation: run });
    const wrapper = open(); await flushPromises(); await click(wrapper, "取消生成");
    expect(studyCommand).toHaveBeenCalledWith("course", { operation: "CANCEL", run_id: "run", session_id: "session" });
  });
});
