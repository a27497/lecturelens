import { describe, expect, it } from "vitest";
import { courseStageText } from "./workspace";

describe("course stage text", () => {
  it("prioritizes terminal status over a stale or empty stage", () => {
    expect(courseStageText("", "CANCELED")).toBe("已取消");
    expect(courseStageText("TRANSLATING", "CANCELED")).toBe("已取消");
    expect(courseStageText("ASR", "FAILED")).toBe("处理失败");
    expect(courseStageText("TRANSLATING", "SUCCEEDED")).toBe("已完成");
  });
});
