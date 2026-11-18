import { afterEach, describe, expect, it, vi } from "vitest";
import { clearLastCourseLocations, forgetLastCourseLocation, lastCourseLocationQuery, readLastCourseLocation, saveLastCourseLocation } from "./lastCourseLocation";

afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear(); });

describe("last course location", () => {
  it("stores only the view names and playback offset, scoped by user and course", () => {
    saveLastCourseLocation(7, "task_a", { view: "tutor", text: "timeline", at: "75000", layout: "classic", draft: "PRIVATE" });
    const stored = Object.entries(window.localStorage).filter(([name]) => name.startsWith("lecturelens.lastCourseLocation"));
    expect(stored).toEqual([["lecturelens.lastCourseLocation.v1:7:task_a", JSON.stringify({ view: "tutor", text: "timeline", at: 75000 })]]);
    expect(readLastCourseLocation(7, "task_a")).toEqual({ view: "tutor", text: "timeline", at: 75000 });
    expect(readLastCourseLocation(8, "task_a")).toBeNull();
    expect(readLastCourseLocation(7, "task_b")).toBeNull();
    expect(lastCourseLocationQuery({ view: "tutor", text: "timeline", at: 75000 })).toEqual({ view: "tutor", text: "timeline", at: "75000" });
  });

  it("does nothing without a known user or course", () => {
    saveLastCourseLocation(null, "task_a", { view: "qa", at: "1" });
    saveLastCourseLocation(7, " ", { view: "qa", at: "1" });
    expect(window.localStorage.length).toBe(0);
    expect(readLastCourseLocation(undefined, "task_a")).toBeNull();
  });

  it.each([
    "not json",
    JSON.stringify({ view: "admin", at: 0 }),
    JSON.stringify({ view: "qa", at: -1 }),
    JSON.stringify({ view: "qa", at: 1.5 }),
    JSON.stringify({ view: "qa" }),
    JSON.stringify(null),
  ])("falls back safely for a malformed entry %s", raw => {
    window.localStorage.setItem("lecturelens.lastCourseLocation.v1:7:task_a", raw);
    expect(readLastCourseLocation(7, "task_a")).toBeNull();
  });

  it("falls back when storage throws", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("denied", "SecurityError"); });
    expect(() => saveLastCourseLocation(7, "task_a", { view: "qa", at: "1" })).not.toThrow();
    expect(readLastCourseLocation(7, "task_a")).toBeNull();
  });

  it("forgets one course and clears every account on logout, leaving other keys alone", () => {
    saveLastCourseLocation(7, "task_a", { view: "qa", at: "1" });
    saveLastCourseLocation(7, "task_b", { view: "tutor", at: "2" });
    saveLastCourseLocation(9, "task_c", { view: "flashcards", at: "3" });
    window.localStorage.setItem("courselingo.userEmail", "keep@example.com");
    forgetLastCourseLocation(7, "task_a");
    expect(readLastCourseLocation(7, "task_a")).toBeNull();
    expect(readLastCourseLocation(7, "task_b")).not.toBeNull();
    clearLastCourseLocations();
    expect(readLastCourseLocation(7, "task_b")).toBeNull();
    expect(readLastCourseLocation(9, "task_c")).toBeNull();
    expect(window.localStorage.getItem("courselingo.userEmail")).toBe("keep@example.com");
  });
});
