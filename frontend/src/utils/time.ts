export function formatSecondsToClock(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainingSeconds = safeSeconds % 60;
  return [hours, minutes, remainingSeconds]
    .map((part) => part.toString().padStart(2, "0"))
    .join(":");
}

export function formatMillisToClock(milliseconds: number): string {
  return formatSecondsToClock(milliseconds / 1000);
}

export function formatMillisRange(startMillis: number, endMillis: number): string {
  return `${formatMillisToClock(startMillis)} - ${formatMillisToClock(endMillis)}`;
}

export function formatDurationBetween(startValue?: string | null, endValue?: string | null): string {
  if (!startValue || !endValue) {
    return "暂无";
  }
  const start = new Date(startValue).getTime();
  const end = new Date(endValue).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return "暂无";
  }
  return formatSecondsToClock((end - start) / 1000);
}
