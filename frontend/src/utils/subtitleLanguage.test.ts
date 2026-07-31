import { describe, expect, it } from "vitest";
import { normalizeSubtitleLanguage } from "./subtitleLanguage";

describe("normalizeSubtitleLanguage", () => {
  it("normalizes ISO 639 aliases and preserves BCP-47 values", () => {
    expect(normalizeSubtitleLanguage("eng")).toBe("en");
    expect(normalizeSubtitleLanguage("zho")).toBe("zh");
    expect(normalizeSubtitleLanguage("chi")).toBe("zh");
    expect(normalizeSubtitleLanguage("en-US")).toBe("en-US");
    expect(normalizeSubtitleLanguage("zh-CN")).toBe("zh-CN");
  });

  it("uses und for missing or automatic language metadata", () => {
    expect(normalizeSubtitleLanguage()).toBe("und");
    expect(normalizeSubtitleLanguage(" ")).toBe("und");
    expect(normalizeSubtitleLanguage("auto")).toBe("und");
    expect(normalizeSubtitleLanguage("und")).toBe("und");
  });
});
