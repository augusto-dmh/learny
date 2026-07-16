/**
 * Browser-side ingestion-status client (FE-18).
 *
 * Reads a source's latest ingestion job + its events through the same-origin
 * Next.js proxy (`/api/...`, ADR-017) so the library can show live progress. A
 * read-only GET, so no CSRF token; the HttpOnly session cookie rides along
 * automatically (`credentials: "same-origin"`). The returned shape mirrors the
 * backend `IngestionSummary` exactly — reused from `sources.ts` (the upload/start
 * client already models it) rather than redeclared here, so the two clients never
 * drift.
 */

import { type IngestionSummary } from "./sources";

export type { IngestionSummary } from "./sources";

/**
 * Fetch a source's latest ingestion job (status/attempts/error + chronological
 * events). On a non-OK response (401 unauthenticated, 404 when no job exists yet)
 * the backend `detail` is surfaced via `toIngestionError`, mirroring `listSources`.
 */
export async function getIngestion(
  sourceId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<IngestionSummary> {
  const res = await fetchImpl(`/api/sources/${sourceId}/ingestion`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toIngestionError(res, "Could not load ingestion status.");
  }
  return (await res.json()) as IngestionSummary;
}

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toIngestionError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
