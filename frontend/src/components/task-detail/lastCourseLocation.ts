import type { LocationQuery } from "vue-router";
import { readCourseLocation } from "./courseLocation";
import type { ContentView } from "./courseLocation";
import type { CourseWorkspace } from "./workspace";
import { isLearningWorkspace } from "./workspace";

// Resume entries are browser-local view coordinates. The APIs still authorize every course read.
const PREFIX = "lecturelens.lastCourseLocation.v1:";

export interface LastCourseLocation {
  view: CourseWorkspace;
  learn?: CourseWorkspace;
  text?: ContentView;
  at: number;
  visitedAt?: number;
}

function key(userId: number, taskId: string) {
  return `${PREFIX}${userId}:${taskId}`;
}

function usable(userId: number | null | undefined, taskId: string): userId is number {
  return typeof userId === "number" && Number.isSafeInteger(userId) && userId > 0 && taskId.trim().length > 0;
}

export function saveLastCourseLocation(userId: number | null | undefined, taskId: string, query: LocationQuery) {
  if (!usable(userId, taskId)) return;
  // readCourseLocation drops unknown views and out-of-range offsets, so only known names are kept.
  const location = readCourseLocation(query);
  const learn = !isLearningWorkspace(location.workspace) && isLearningWorkspace(query.learn) ? location.learningWorkspace : undefined;
  const current = readLastCourseLocation(userId, taskId);
  if (current?.visitedAt && current.view === location.workspace && current.text === location.textView && current.at === location.milliseconds && current.learn === learn) return;
  const value: LastCourseLocation = {
    view: location.workspace,
    ...(learn ? { learn } : {}),
    ...(location.textView ? { text: location.textView } : {}),
    at: location.milliseconds,
    visitedAt: Date.now(),
  };
  try { window.localStorage.setItem(key(userId, taskId), JSON.stringify(value)); }
  catch { /* Storage unavailable: the list falls back to the default entry. */ }
}

export function readLastCourseLocation(userId: number | null | undefined, taskId: string): LastCourseLocation | null {
  if (!usable(userId, taskId)) return null;
  try {
    const raw = window.localStorage.getItem(key(userId, taskId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || typeof parsed.view !== "string" || typeof parsed.at !== "number") return null;
    const location = readCourseLocation({ view: parsed.view, text: typeof parsed.text === "string" ? parsed.text : null, at: String(parsed.at) });
    if (location.workspace !== parsed.view || location.milliseconds !== parsed.at) return null;
    return { view: location.workspace, ...(isLearningWorkspace(parsed.learn) ? { learn: parsed.learn } : {}), ...(location.textView ? { text: location.textView } : {}), at: location.milliseconds, ...(typeof parsed.visitedAt === "number" && Number.isSafeInteger(parsed.visitedAt) && parsed.visitedAt > 0 ? { visitedAt: parsed.visitedAt } : {}) };
  } catch {
    return null;
  }
}

export function lastCourseLocationQuery(location: LastCourseLocation): Record<string, string> {
  return { view: location.view, ...(location.learn ? { learn: location.learn } : {}), ...(location.text ? { text: location.text } : {}), at: String(location.at) };
}

export function forgetLastCourseLocation(userId: number | null | undefined, taskId: string) {
  if (!usable(userId, taskId)) return;
  try { window.localStorage.removeItem(key(userId, taskId)); } catch { /* ignore */ }
}

/** Called on logout: removes the entries of every user that signed in on this browser. */
export function clearLastCourseLocations() {
  try {
    const keys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index++) {
      const name = window.localStorage.key(index);
      if (name?.startsWith(PREFIX)) keys.push(name);
    }
    keys.forEach(name => window.localStorage.removeItem(name));
  } catch { /* ignore */ }
}
