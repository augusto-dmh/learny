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

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toSourceError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: string };
    return new Error(body.detail ?? fallback);
  } catch {
    return new Error(fallback);
  }
}
