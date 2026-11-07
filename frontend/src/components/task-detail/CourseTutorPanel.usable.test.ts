import { flushPromises, mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import CourseTutorPanel from "./CourseTutorPanel.vue";
import { getTutorSession, listTutorSessions, submitTutorTurn } from "../../api/tutor";
import type { TutorSession, TutorTurn } from "../../api/tutor";

vi.mock("../../api/tutor", () => ({ cancelTutorTurn: vi.fn(), createTutorSession: vi.fn(), getTutorSession: vi.fn(), listTutorSessions: vi.fn(), submitTutorTurn: vi.fn() }));

it("restores full v18-sized Unicode/code/feedback with escaped HTML and bound canonical citations", async () => {
  const id = "a".repeat(64);
  const session: TutorSession = { session_id: "s18", revision: 7, status: "active", model_calls: 60, max_calls: 60 };
  const code = "\n```python\nvalues = ['Ada', 'Grace']\nprint(values[0]) # teaching comment\n```\n<img src=x onerror=bad()>";
  const answer = "中😀".repeat(1700) + code + ` [${id}]`;
  const evaluation = "反馈".repeat(440) + ` [${id}]`;
  const turn: TutorTurn = { turn_id: "t18", client_turn_id: "k18", ordinal: 1, learner_text: "Explain indexing", socratic: false,
    status: "completed", outcome: "answered", answer, evaluation, error_code: null,
    citations: [{ evidence_id: id, text: "values[0] selects the first value.", start_ms: 1000, end_ms: 2000, source_type: "SUBTITLE" }] };
  vi.mocked(listTutorSessions).mockResolvedValue({ sessions: [session], revision: 7 });
  vi.mocked(getTutorSession).mockResolvedValue({ session, turns: [turn] });
  const w = mount(CourseTutorPanel, { props: { taskId: "synthetic-course" } });
  try {
    await flushPromises();
    const paragraphs = w.findAll(".answer > p");
    expect(paragraphs[0]!.element.textContent).toBe(answer);
    expect(paragraphs[1]!.element.textContent).toBe("对你的回复：" + evaluation);
    expect(w.find("img").exists()).toBe(false);
    await w.find(".citation").trigger("click");
    expect(w.emitted("seek")).toEqual([[1000, { evidenceId: id, revision: 7 }]]);
    expect(submitTutorTurn).not.toHaveBeenCalled();
  } finally { w.unmount(); }
});
