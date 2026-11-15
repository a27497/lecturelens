import { describe, expect, it } from "vitest";
import { courseLearnable, courseStageText } from "./workspace";

describe("course stage text", () => {
  it("prioritizes terminal status over a stale or empty stage", () => {
    expect(courseStageText("", "CANCELED")).toBe("已取消");
    expect(courseStageText("TRANSLATING", "CANCELED")).toBe("已取消");
    expect(courseStageText("ASR", "FAILED")).toBe("处理失败");
    expect(courseStageText("TRANSLATING", "SUCCEEDED")).toBe("已完成");
  });
});

describe("course learnability", () => {
  it("opens learning when subtitles are ready on a running course, mirroring the backend rule", () => {
    expect(courseLearnable("SUCCEEDED", null)).toBe(true);
    expect(courseLearnable("RUNNING", true)).toBe(true);
    expect(courseLearnable("RUNNING", false)).toBe(false);
    expect(courseLearnable("RUNNING", undefined)).toBe(false);
    for (const status of ["CREATED", "QUEUED", "RETRYING", "FAILED", "CANCELED"]) {
      expect(courseLearnable(status, true)).toBe(false);
    }
  });
});
