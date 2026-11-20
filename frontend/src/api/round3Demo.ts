import { shallowRef } from "vue";
import type { LoginResponse } from "./auth";
import { authHeader } from "./authToken";
import type { CourseNote } from "../components/task-detail/courseNotes";

export const round3Enabled = import.meta.env.VITE_ROUND3_DEMO === "true";

interface DemoCourse {
  taskId: string;
  title: string;
  series: string;
  description: string;
  durationMs: number;
  positionMs: number;
  learningPercent: number;
  cover: string;
  notes: CourseNote[];
  followups: string[];
  questions: string[];
  topics: Array<{ question: string; title: string }>;
}

export const round3Course = shallowRef<DemoCourse>();

export async function enterRound3(): Promise<LoginResponse> {
  const response = await fetch("/api/round3/entry", { method: "POST", cache: "no-store" });
  if (!response.ok) throw Error("演示课程暂时无法打开");
  return response.json();
}

export async function loadRound3Course() {
  const response = await fetch("/api/round3/course", { headers: authHeader(), cache: "no-store" });
  const course: DemoCourse | undefined = response.ok ? await response.json() : undefined;
  round3Course.value = course;
  return course;
}

export async function readDemoPracticeExplanation(artifactId: string, index: number, signal: AbortSignal) {
  const response = await fetch(`/api/round3/practice/${encodeURIComponent(artifactId)}/${index}`, {
    headers: authHeader(), cache: "no-store", signal,
  });
  if (!response.ok) throw Error("解析暂时无法打开");
  return (await response.json() as { explanation: string }).explanation;
}
