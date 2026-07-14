export type SubtitleCue = {
  start: number;
  end: number;
  text: string;
};

const TIMING_SEPARATOR = "-->";
const SKIPPED_BLOCK_PREFIXES = ["NOTE", "STYLE", "REGION"];

export function parseVttCues(vttText: string): SubtitleCue[] {
  return vttText
    .replace(/^\uFEFF/, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split(/\n{2,}/)
    .flatMap(parseCueBlock);
}

function parseCueBlock(block: string): SubtitleCue[] {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return [];
  }

  const firstLine = lines[0].toUpperCase();
  if (firstLine === "WEBVTT" || firstLine.startsWith("WEBVTT ")) {
    return parseCueBlock(lines.slice(1).join("\n"));
  }
  if (SKIPPED_BLOCK_PREFIXES.some((prefix) => firstLine === prefix || firstLine.startsWith(`${prefix} `))) {
    return [];
  }

  const timingLineIndex = lines.findIndex((line) => line.includes(TIMING_SEPARATOR));
  if (timingLineIndex < 0) {
    return [];
  }

  const timing = parseTimingLine(lines[timingLineIndex]);
  if (!timing) {
    return [];
  }

  const text = lines.slice(timingLineIndex + 1).join("\n").trim();
  if (!text) {
    return [];
  }

  return [{ ...timing, text }];
}

function parseTimingLine(line: string): Pick<SubtitleCue, "start" | "end"> | null {
  const [startValue, endWithSettings] = line.split(TIMING_SEPARATOR);
  const endValue = endWithSettings?.trim().split(/\s+/)[0] ?? "";
  const start = parseTimestamp(startValue.trim());
  const end = parseTimestamp(endValue.trim());
  if (start === null || end === null || end < start) {
    return null;
  }
  return { start, end };
}

function parseTimestamp(value: string): number | null {
  const normalized = value.replace(",", ".");
  const parts = normalized.split(":");
  if (parts.length !== 2 && parts.length !== 3) {
    return null;
  }

  const secondsPart = Number(parts[parts.length - 1]);
  const minutes = Number(parts[parts.length - 2]);
  const hours = parts.length === 3 ? Number(parts[0]) : 0;
  if (![hours, minutes, secondsPart].every(Number.isFinite)) {
    return null;
  }

  return hours * 3600 + minutes * 60 + secondsPart;
}
