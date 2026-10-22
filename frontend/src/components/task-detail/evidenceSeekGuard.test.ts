import { expect, it, vi } from "vitest";
import { createEvidenceSeekGuard } from "./evidenceSeekGuard";
const context = { evidenceId: "canonical-r1", revision: 1 };
function deferred() {
  let resolve!: (value: number) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<number>((ok, no) => { resolve = ok; reject = no; });
  return { promise, resolve, reject };
}
it("checks the authoritative source revision before applying an evidence position", async () => {
  const pending = deferred(), read = vi.fn(() => pending.promise), apply = vi.fn(), fail = vi.fn();
  const guard = createEvidenceSeekGuard(read, fail);
  const work = guard.seek("course", context, apply);
  expect(apply).not.toHaveBeenCalled(); expect(read).toHaveBeenCalledWith("course");
  pending.resolve(1); await work;
  expect(apply).toHaveBeenCalledOnce(); expect(fail).not.toHaveBeenCalled();
});
it("does not navigate an old citation onto a replacement source", async () => {
  const apply = vi.fn(), fail = vi.fn();
  await createEvidenceSeekGuard(async () => 2, fail).seek("course", context, apply);
  expect(apply).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledWith(expect.stringContaining("课程资料已更新"));
});
it.each([{}, { evidenceId: "canonical" }, { evidenceId: "canonical", revision: -1 }, { evidenceId: "canonical", revision: NaN }])("rejects unversioned/invalid evidence %s", async supplied => {
  const read = vi.fn(async () => 1), apply = vi.fn(), fail = vi.fn();
  await createEvidenceSeekGuard(read, fail).seek("course", supplied, apply);
  expect(read).not.toHaveBeenCalled(); expect(apply).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledOnce();
});
it("leaves learning state intact when authorization or verification fails", async () => {
  const apply = vi.fn(), fail = vi.fn();
  await createEvidenceSeekGuard(async () => { throw Error("404 or unavailable"); }, fail).seek("course", context, apply);
  expect(apply).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledWith(expect.stringContaining("无法核实"));
});
it("only applies the newest request when revision checks complete out of order", async () => {
  const first = deferred(), second = deferred(), read = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const a = vi.fn(), b = vi.fn(), fail = vi.fn(), guard = createEvidenceSeekGuard(read, fail);
  const one = guard.seek("course", context, a), two = guard.seek("course", context, b);
  second.resolve(1); await two; first.resolve(2); await one;
  expect(a).not.toHaveBeenCalled(); expect(b).toHaveBeenCalledOnce(); expect(fail).not.toHaveBeenCalled();
});
it("cancels late success and failure after a course or view change", async () => {
  for (const success of [true, false]) {
    const pending = deferred(), apply = vi.fn(), fail = vi.fn(), guard = createEvidenceSeekGuard(() => pending.promise, fail);
    const work = guard.seek("old-course", context, apply); guard.cancel();
    if (success) pending.resolve(1); else pending.reject(Error("late failure"));
    await work; expect(apply).not.toHaveBeenCalled(); expect(fail).not.toHaveBeenCalled();
  }
});
it("allows current transcript/chapter seeks to supersede a pending citation without extra I/O", async () => {
  const pending = deferred(), read = vi.fn(() => pending.promise), a = vi.fn(), b = vi.fn(), fail = vi.fn();
  const guard = createEvidenceSeekGuard(read, fail), one = guard.seek("course", context, a);
  await guard.seek("course", undefined, b); pending.resolve(1); await one;
  expect(a).not.toHaveBeenCalled(); expect(b).toHaveBeenCalledOnce(); expect(read).toHaveBeenCalledOnce();
});

it("publishes a fresh transcript and position only after both source fences pass", async () => {
  const calls: string[] = [], read = vi.fn(async () => { calls.push("check"); return 1; });
  const guard = createEvidenceSeekGuard(read, vi.fn(), async () => { calls.push("read"); return () => { calls.push("publish"); }; });
  await guard.seek("course", context, () => { calls.push("seek"); });
  expect(calls).toEqual(["check", "read", "check", "publish", "seek"]);
});
it("rejects a source replacement during transcript loading", async () => {
  const publish = vi.fn(), apply = vi.fn(), fail = vi.fn(), read = vi.fn().mockResolvedValueOnce(1).mockResolvedValueOnce(2);
  await createEvidenceSeekGuard(read, fail, async () => publish).seek("course", context, apply);
  expect(publish).not.toHaveBeenCalled(); expect(apply).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledOnce();
});
it("discards transcript work completed after a navigation cancellation", async () => {
  let complete!: (publish: () => void) => void;
  const pending = new Promise<() => void>(resolve => { complete = resolve; });
  const publish = vi.fn(), apply = vi.fn(), read = vi.fn(async () => 1), guard = createEvidenceSeekGuard(read, vi.fn(), () => pending);
  const work = guard.seek("course", context, apply);
  await Promise.resolve(); guard.cancel(); complete(publish); await work;
  expect(publish).not.toHaveBeenCalled(); expect(apply).not.toHaveBeenCalled(); expect(read).toHaveBeenCalledOnce();
});
