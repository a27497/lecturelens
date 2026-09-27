import { afterEach, expect, it, vi } from "vitest";
import { randomUuid } from "./randomUuid";

afterEach(() => vi.unstubAllGlobals());

it("generates a version 4 id when randomUUID is unavailable on HTTP", () => {
  let next = 0;
  vi.stubGlobal("crypto", {
    getRandomValues: (bytes: Uint8Array) => bytes.map(() => next++),
  });

  expect(randomUuid()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
