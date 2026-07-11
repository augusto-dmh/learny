/**
 * Browser-side sources client (T7, SRC-11).
 *
 * Thin helpers the sources screen uses to talk to FastAPI *through the
 * same-origin Next.js proxy* (`/api/...`, ADR-017) — never cross-origin. The
 * HttpOnly session cookie rides along automatically (`credentials:
 * "same-origin"`), so this code never reads or holds the session token. The
 * only token JS handles is the CSRF token (from `/api/auth/me`), echoed in
 * `X-CSRF-Token` on the state-changing upload (AD-007), mirroring `auth.ts`.
 *
 * FastAPI remains authoritative for auth, ownership, and validation; these
 * helpers just carry inputs in and surface success/error out.
 */

/** Secret-free source summary as returned by `/api/sources*`. */
export type SourceSummary = {
  id: string;
  title: string;
  filename: string;
  byte_size: number;
  content_type: string;
  status: string;
  created_at: string;
};

/** One progress-log entry, as returned in an `IngestionSummary`. */
export type IngestionEventView = {
  type: string;
  message: string | null;
  created_at: string;
};

/**
 * Secret-free ingestion job view as returned by `/api/sources/{id}/ingestion`.
 * Mirrors the backend `IngestionSummary`: job lifecycle state only, never the
 * source's `object_key`/`checksum`.
 */
export type IngestionSummary = {
  id: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  events: IngestionEventView[];
};

/**
 * One node in a source's parsed section tree (CORP-11), nested per the TOC
 * hierarchy. Mirrors the backend `StructureSectionView`.
 */
export type StructureSection = {
  title: string;
  depth: number;
  section_path: string[];
  anchor: string;
  children: StructureSection[];
};

/**
 * A source's parsed book structure as returned by
 * `/api/sources/{id}/structure`. Mirrors the backend `BookStructureView`:
 * `title`/`language` are null and `authors` empty when the OPF omitted them.
 */
export type SourceStructure = {
  title: string | null;
  authors: string[];
  language: string | null;
  sections: StructureSection[];
};

/** List the caller's sources (newest-first), or `[]` when they have none. */
export async function listSources(
  fetchImpl: typeof fetch = fetch,
): Promise<SourceSummary[]> {
  const res = await fetchImpl("/api/sources", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toSourceError(res, "Could not load your sources.");
  }
  return (await res.json()) as SourceSummary[];
}

/** Fetch one source the caller owns. */
export async function getSource(
  id: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SourceSummary> {
  const res = await fetchImpl(`/api/sources/${id}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toSourceError(res, "Could not load that source.");
  }
  return (await res.json()) as SourceSummary;
}

/**
 * Upload an EPUB with a title. This is a state-changing request, so it carries
 * the session-bound CSRF token in `X-CSRF-Token` (AD-007); the caller passes it
 * in (read from `/api/auth/me`), same as `logout(csrfToken)`. The body is real
 * multipart `FormData` (file + title) — we deliberately do NOT set a
 * `Content-Type`, letting the browser add the multipart boundary itself.
 */
export async function uploadSource(
  file: File,
  title: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SourceSummary> {
  const body = new FormData();
  body.set("file", file);
  body.set("title", title);
  const res = await fetchImpl("/api/sources", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
    body,
  });
  if (!res.ok) {
    throw await toSourceError(res, "Upload failed.");
  }
  return (await res.json()) as SourceSummary;
}

/**
 * Start ingestion for an uploaded source. This is a state-changing request, so
 * it carries the session-bound CSRF token in `X-CSRF-Token` (AD-007), same as
 * `uploadSource`; the caller passes it in (read from `/api/auth/me`). The
 * HttpOnly session cookie rides along automatically (`credentials:
 * "same-origin"`). On a non-OK response (e.g. 409 "already in progress", 502),
 * the backend `detail` is surfaced via `toSourceError`.
 */
export async function startIngestion(
  sourceId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<IngestionSummary> {
  const res = await fetchImpl(`/api/sources/${sourceId}/ingestion`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await toSourceError(res, "Could not start ingestion.");
  }
  return (await res.json()) as IngestionSummary;
}

/**
 * Fetch a source's parsed book structure (metadata + nested section tree)
 * through the same-origin proxy. Read-only GET, so no CSRF token; the HttpOnly
 * session cookie rides along automatically. Non-OK responses (e.g. 404 when the
 * source has no corpus yet) surface the backend `detail` via `toSourceError`,
 * mirroring `listSources`.
 */
export async function fetchSourceStructure(
  id: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SourceStructure> {
  const res = await fetchImpl(`/api/sources/${id}/structure`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toSourceError(res, "Could not load the book structure.");
  }
  return (await res.json()) as SourceStructure;
}

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toSourceError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: string };
    return new Error(body.detail ?? fallback);
  } catch {
    return new Error(fallback);
  }
}
