import type { EvidenceIndexStatus } from "../../api/qa";

/**
 * Mirrors the backend rule: READY, or a same-revision catch-up (e.g. translations finishing in the
 * background) whose previous index still covers every evidence item a session may cite.
 */
export function evidenceIndexServable(index: Pick<EvidenceIndexStatus, "status"> & Partial<Pick<EvidenceIndexStatus, "revision" | "indexedRevision">>): boolean {
  if (index.status === "READY") return true;
  return ["PENDING", "INDEXING", "FAILED"].includes(index.status)
    && index.indexedRevision !== null && index.indexedRevision !== undefined
    && index.indexedRevision === index.revision;
}
