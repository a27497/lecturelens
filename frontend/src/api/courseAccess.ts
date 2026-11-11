// A failed subordinate record may be missing while the course still exists.
// Callers recheck the owning course before clearing the whole workspace.
export function mayHaveLostCourseAccess(error: unknown): boolean {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status !== undefined && [401, 403, 404].includes(status);
}
