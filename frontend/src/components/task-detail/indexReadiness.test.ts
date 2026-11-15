import { describe, expect, it } from "vitest";
import { evidenceIndexServable } from "./indexReadiness";

describe("evidence index servability", () => {
  it("serves a same-revision catch-up but never another revision's index", () => {
    expect(evidenceIndexServable({ status: "READY", revision: 2, indexedRevision: 2 })).toBe(true);
    expect(evidenceIndexServable({ status: "PENDING", revision: 2, indexedRevision: 2 })).toBe(true);
    expect(evidenceIndexServable({ status: "INDEXING", revision: 2, indexedRevision: 2 })).toBe(true);
    expect(evidenceIndexServable({ status: "FAILED", revision: 2, indexedRevision: 2 })).toBe(true);
    expect(evidenceIndexServable({ status: "PENDING", revision: 3, indexedRevision: 2 })).toBe(false);
    expect(evidenceIndexServable({ status: "PENDING", revision: 1, indexedRevision: null })).toBe(false);
    expect(evidenceIndexServable({ status: "INDEXING" })).toBe(false);
    expect(evidenceIndexServable({ status: "DISABLED", revision: 1, indexedRevision: 1 })).toBe(false);
  });
});
