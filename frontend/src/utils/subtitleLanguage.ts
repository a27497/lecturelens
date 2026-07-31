export function normalizeSubtitleLanguage(language?: string) {
  const value = language?.trim() || "";
  if (!value || ["und", "auto"].includes(value.toLowerCase())) return "und";
  const lower = value.toLowerCase();
  if (lower === "eng") return "en";
  if (lower === "zho" || lower === "chi") return "zh";
  return value;
}
