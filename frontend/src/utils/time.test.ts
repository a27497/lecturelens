import { describe, expect, it } from "vitest";
import { formatDurationBetween, parseApiTimestamp } from "./time";

describe("API timestamp helpers", () => {
  it("treats legacy timestamps without an offset as UTC", () => {
    expect(parseApiTimestamp("2026-07-31T03:47:20.069")?.toISOString())
      .toBe("2026-07-31T03:47:20.069Z");
  });

  it("normalizes UTC, Asia/Taipei offsets, and daylight-saving offsets", () => {
    expect(parseApiTimestamp("2026-07-31T03:47:20.069Z")?.toISOString())
      .toBe("2026-07-31T03:47:20.069Z");
    expect(parseApiTimestamp("2026-07-31T11:47:20.069+08:00")?.toISOString())
      .toBe("2026-07-31T03:47:20.069Z");
    expect(parseApiTimestamp("2026-07-30T23:47:20.069-04:00")?.toISOString())
      .toBe("2026-07-31T03:47:20.069Z");
  });

  it("does not display a negative duration", () => {
    expect(formatDurationBetween("2026-07-31T04:00:00Z", "2026-07-31T03:00:00Z"))
      .toBe("暂无");
  });
});
