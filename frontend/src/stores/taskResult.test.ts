import { beforeEach, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useTaskResultStore } from "./taskResult";
import { fetchTaskResult } from "../api/result";
import type { TaskResultResponse } from "../types/result";
vi.mock("../api/result", () => ({ fetchTaskResult: vi.fn(), toReadableTaskResultError: () => "unavailable" }));
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); });
const result = (taskId: string, sourceFullText: string) => ({ taskId, sourceFullText } as TaskResultResponse);
it("prevents an old in-flight result from overwriting the verified evidence transcript", async () => {
  let finish!: (result: TaskResultResponse) => void;
  vi.mocked(fetchTaskResult).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const store = useTaskResultStore(), work = store.load("course");
  store.acceptVerified("course", result("course", "verified revision"));
  finish(result("course", "old source")); await work;
  expect(store.result?.sourceFullText).toBe("verified revision"); expect(store.loading).toBe(false);
});
it("rejects publication for another course or an unexpected response identity", () => {
  const store = useTaskResultStore(); store.taskId = "next-course";
  store.acceptVerified("old-course", result("old-course", "private old source"));
  store.acceptVerified("next-course", result("old-course", "mismatched source"));
  expect(store.result).toBeNull(); expect(store.taskId).toBe("next-course");
});
