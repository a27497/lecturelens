export type EvidenceSeekContext = { evidenceId?: string | null; revision?: number | null };

/** Recheck the source epoch without changing saved learning state or starting a Run. */
export function createEvidenceSeekGuard(readRevision: (taskId: string) => Promise<number>, fail: (message: string) => void) {
  let generation = 0;
  return {
    cancel() { generation++; },
    async seek(taskId: string, context: EvidenceSeekContext | undefined, apply: () => void) {
      const current = ++generation;
      if (context) {
        if (!context.evidenceId || !Number.isSafeInteger(context.revision) || context.revision! < 0) {
          fail("这条证据缺少课程版本，暂不能定位。请重新核对课程来源；当前输入和作答仍保留。");
          return;
        }
        try {
          const revision = await readRevision(taskId);
          if (current !== generation) return;
          if (revision !== context.revision) {
            fail("课程资料已更新，旧证据暂不能定位。请使用更新后的课程重新核对；当前输入和作答仍保留。");
            return;
          }
        } catch {
          if (current === generation) fail("无法核实课程证据，请重试或刷新课程。当前输入和作答仍保留。");
          return;
        }
      }
      if (current === generation) apply();
    },
  };
}
