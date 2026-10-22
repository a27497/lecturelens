import { beforeEach, expect, it, vi } from "vitest";
import { http } from "./http";
import { studyCommand } from "./study";
import { askCourseQa } from "./qa";
import type { LearningScope } from "./learningScope";
vi.mock("./http", () => ({ http: { post: vi.fn() } }));
vi.mock("./authToken", () => ({ authHeader: () => ({}) }));
const scopes: LearningScope[] = [
  { version: 1, kind: "segments", policy: "strict", revision: 1, evidence_ids: ["e1"] },
  { version: 1, kind: "segments", policy: "course", revision: 1, evidence_ids: ["e1"] },
  { version: 1, kind: "course", policy: "strict", revision: 1, evidence_ids: [] },
];
beforeEach(() => { vi.resetAllMocks(); vi.mocked(http.post).mockResolvedValue({ data: { data: {} } }); });
it.each(scopes)("uses a scope-aware route for explicit scope %j", async learning_scope => {
  await studyCommand("course", { operation: "START", learning_scope });
  await askCourseQa("course", { question: "Explain", learning_scope });
  expect(vi.mocked(http.post).mock.calls.map(call => call[0])).toEqual(["/api/tasks/course/study/scoped-command", "/api/tasks/course/qa/scoped"]);
});
it("preserves legacy routing for commands and QA without an explicit scope", async () => {
  await studyCommand("course", { operation: "CREATE_SESSION" });
  await askCourseQa("course", { question: "Legacy question" });
  expect(vi.mocked(http.post).mock.calls.map(call => call[0])).toEqual(["/api/tasks/course/study/command", "/api/tasks/course/qa"]);
});
it.each(["study", "qa"])("fails without falling back when %s reaches an old gateway", async kind => {
  const error = { response: { status: 404 } };
  vi.mocked(http.post).mockRejectedValueOnce(error);
  const result = kind === "study" ? studyCommand("course", { operation: "START", learning_scope: scopes[0]! }) : askCourseQa("course", { question: "Explain", learning_scope: scopes[0]! });
  await expect(result).rejects.toBe(error);
  expect(http.post).toHaveBeenCalledTimes(1);
  expect(vi.mocked(http.post).mock.calls[0]![0]).toContain(kind === "study" ? "scoped-command" : "qa/scoped");
});
