export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

export function getFileExtension(filename: string): string {
  const lastDotIndex = filename.lastIndexOf(".");
  if (lastDotIndex < 0 || lastDotIndex === filename.length - 1) {
    return "";
  }
  return filename.slice(lastDotIndex + 1).toLowerCase();
}
