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
  const start = parseApiTimestamp(startValue)?.getTime() ?? Number.NaN;
  const end = parseApiTimestamp(endValue)?.getTime() ?? Number.NaN;
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return "暂无";
  }
  return formatSecondsToClock((end - start) / 1000);
}

export function parseApiTimestamp(value?: string | null): Date | null {
  if (!value) return null;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim())
    ? value.trim()
    : `${value.trim()}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatApiTimestamp(value?: string | null): string {
  if (!value) return "暂无";
  const parsed = parseApiTimestamp(value);
  return parsed ? parsed.toLocaleString() : value;
}
