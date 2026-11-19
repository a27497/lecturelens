import type { LocationQuery } from "vue-router";
import { DEFAULT_LEARNING_WORKSPACE, isLearningWorkspace, WORKSPACE_ITEMS } from "./workspace";

export type ContentView = "translated" | "source" | "timeline" | "visual" | "chapters";
export type SeekRequest = { milliseconds: number; sequence: number; pause?: boolean };
const textViews: ContentView[] = ["translated", "source", "timeline", "visual", "chapters"];
// A bounded URL coordinate, independent of signed media URLs or learning data.
export const MAX_POSITION_MS = 7 * 24 * 60 * 60 * 1000;
export function validPosition(value: number): boolean {
  return Number.isSafeInteger(value) && value >= 0 && value <= MAX_POSITION_MS;
}
export function readCourseLocation(query: LocationQuery) {
  const workspace = WORKSPACE_ITEMS.find(item => item.value === query.view)?.value ?? DEFAULT_LEARNING_WORKSPACE;
  const learningWorkspace = isLearningWorkspace(workspace) ? workspace :
    isLearningWorkspace(query.learn) ? query.learn : DEFAULT_LEARNING_WORKSPACE;
  const textView = typeof query.text === "string" && textViews.includes(query.text as ContentView) ? query.text as ContentView : undefined;
  const at = typeof query.at === "string" && /^\d{1,9}$/.test(query.at) ? Number(query.at) : 0;
  return { workspace, learningWorkspace, textView, milliseconds: validPosition(at) ? at : 0, classic: query.layout === "classic" };
}
