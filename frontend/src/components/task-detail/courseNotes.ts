import { validPosition } from "./courseLocation";

export type NoteAnchor =
  | { kind: "playback"; milliseconds: number }
  | { kind: "evidence"; milliseconds: number; evidenceId: string; revision: number };

export interface CourseNote {
  id: string;
  text: string;
  anchor: NoteAnchor | null;
}

export function courseNotesKey(userId: number, taskId: string) {
  return `lecturelens.courseNotes.v1:${userId}:${encodeURIComponent(taskId)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readAnchor(value: unknown): NoteAnchor | null {
  if (value === null) return null;
  if (isRecord(value) && typeof value.milliseconds === "number" && validPosition(value.milliseconds)) {
    const { kind, milliseconds, evidenceId, revision } = value;
    if (kind === "playback") return { kind, milliseconds };
    if (kind === "evidence" && typeof evidenceId === "string" && evidenceId.trim()
      && typeof revision === "number" && Number.isSafeInteger(revision) && revision >= 0) {
      return { kind, milliseconds, evidenceId, revision };
    }
  }
  throw new Error("Invalid note anchor");
}

export function readCourseNotes(storage: Storage, key: string): CourseNote[] {
  const raw = storage.getItem(key);
  if (raw === null) return [];
  const values: unknown = JSON.parse(raw);
  if (!Array.isArray(values)) throw new Error("Invalid course notes");
  const ids = new Set<string>();
  return values.map((value: unknown) => {
    if (!isRecord(value) || typeof value.id !== "string" || !value.id.trim() || ids.has(value.id)
      || typeof value.text !== "string" || !value.text.trim()) {
      throw new Error("Invalid course note");
    }
    ids.add(value.id);
    return { id: value.id, text: value.text, anchor: readAnchor(value.anchor) };
  });
}

export function updateCourseNotes(storage: Storage, key: string, change: (notes: CourseNote[]) => CourseNote[]) {
  const notes = change(readCourseNotes(storage, key));
  storage.setItem(key, JSON.stringify(notes));
  return notes;
}
