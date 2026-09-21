import { expect, it } from "vitest";
import { groupModelVersions, modelGuide } from "./modelDiscovery";

it("does not certify unknown providers or mistake multimodal/coder models for specialized endpoints", () => {
  expect(modelGuide("qwen3.8-max").category).toBe("unknown");
  expect(modelGuide("qwen3.8-max").capability).toBeUndefined();
  expect(modelGuide("qwen3.8-max", true).capability).toBe("官方支持工具调用");
  for (const name of ["qwen3-coder-plus", "qwen-vl-plus", "custom-chat", "qwen3.8-omni-flash"]) {
    expect(modelGuide(name, true).category).not.toBe("other");
  }
  for (const name of ["text-embedding-v4", "qwen3-rerank", "qwen3.8-livetranslate-flash-realtime", "whisper-audio", "wan2.2-t2v"]) {
    expect(modelGuide(name, true).category).toBe("other");
  }
});

it("groups only date suffixes and preserves real IDs including snapshot-only families", () => {
  expect(groupModelVersions(["qwen-plus-2026-01-01", "qwen-plus", "qwen3.8-max-0902", "qwen3.8-max-0812", "qwen3-30b-a3b"], false)).toEqual([
    { id: "qwen-plus", versions: ["qwen-plus-2026-01-01"] },
    { id: "qwen3.8-max-0902", versions: ["qwen3.8-max-0812"] },
    { id: "qwen3-30b-a3b", versions: [] },
  ]);
  expect(groupModelVersions(["qwen-plus", "qwen-plus-2026-01-01"], true)).toHaveLength(2);
});
