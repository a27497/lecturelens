import type { LocationQuery } from "vue-router";
import { WORKSPACE_ITEMS } from "./workspace";

export type ContentView = "translated" | "source" | "timeline" | "visual";
export type SeekRequest = { milliseconds: number; sequence: number };
const textViews: ContentView[] = ["translated", "source", "timeline", "visual"];
// A bounded URL coordinate, independent of signed media URLs or learning data.
export const MAX_POSITION_MS = 7 * 24 * 60 * 60 * 1000;
export function validPosition(value: number): boolean {
  return Number.isSafeInteger(value) && value >= 0 && value <= MAX_POSITION_MS;
}
export function readCourseLocation(query: LocationQuery) {
  const workspace = WORKSPACE_ITEMS.find(item => item.value === query.view)?.value ?? "agent";
  const textView = typeof query.text === "string" && textViews.includes(query.text as ContentView) ? query.text as ContentView : undefined;
  const at = typeof query.at === "string" && /^\d{1,9}$/.test(query.at) ? Number(query.at) : 0;
  return { workspace, textView, milliseconds: validPosition(at) ? at : 0, classic: query.layout === "classic" };
}
