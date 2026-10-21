import { describe, expect, it } from "vitest";
import { createTimeIndex } from "./timeIndex";

describe("time index", () => {
  const ranges = [{ start: 100, end: 400 }, { start: 200, end: 250 }, { start: 400, end: 500 }];
  const at = createTimeIndex(ranges, r => r.start, r => r.end);
  it("uses half-open millisecond boundaries and restores the enclosing overlap", () => {
    expect(at(99)).toBeNull(); expect(at(100)).toBe(ranges[0]);
    expect(at(200)).toBe(ranges[1]); expect(at(249)).toBe(ranges[1]);
    expect(at(250)).toBe(ranges[0]); expect(at(399)).toBe(ranges[0]);
    expect(at(400)).toBe(ranges[2]); expect(at(500)).toBeNull();
  });
  it("keeps gaps empty and resolves equal starts in original order", () => {
    const a = { start: 0, end: 5 }, b = { start: 0, end: 10 }, c = { start: 20, end: 30 };
    const lookup = createTimeIndex([c, a, b], r => r.start, r => r.end);
    expect(lookup(2)).toBe(a); expect(lookup(5)).toBe(b); expect(lookup(15)).toBeNull();
  });
  it("excludes empty, inverted and invalid ranges", () => {
    const lookup = createTimeIndex([{ start: 0, end: 0 }, { start: 5, end: 1 }, { start: -1, end: 4 }, { start: 0, end: NaN }], r => r.start, r => r.end);
    for (const time of [0, 2, -1, NaN, Infinity]) expect(lookup(time)).toBeNull();
  });
  it("matches a linear oracle on a large unsorted overlapping timeline", () => {
    const rows = Array.from({ length: 10_000 }, (_, i) => ({ start: (i * 7919 % 10_000) * 100, end: (i * 7919 % 10_000) * 100 + (i % 27 + 1) * 60 }));
    const lookup = createTimeIndex(rows, r => r.start, r => r.end);
    for (let time = 0; time < 1_002_000; time += 1307) {
      const expected = rows.filter(r => r.start <= time && r.end > time).sort((a, b) => b.start - a.start)[0] ?? null;
      expect(lookup(time)).toBe(expected);
    }
  });
});
