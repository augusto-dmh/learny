/**
 * Browser-side notes + highlights client (NF-11).
 *
 * Thin helpers the notes screens and the reader's capture popover use to drive
 * whole-Markdown notes and book highlights against FastAPI *through the same-origin
 * Next.js proxy* (`/api/...`, ADR-017) — never cross-origin. The HttpOnly session
 * cookie rides along automatically (`credentials: "same-origin"`), so this code
 * never reads or holds the session token. The reads (list, detail, backlinks)
 * carry no token; the state-changing writes (create, update, delete, capture) echo
 * the CSRF token (from `/api/auth/me`) in `X-CSRF-Token` (AD-007), mirroring
 * `quiz.ts`.
 *
 * FastAPI remains authoritative for auth, ownership, anchor resolution, and the
 * body cap; these helpers just carry inputs in and surface the note/summary/
 * backlink/error out. The response types mirror the backend views in `web/notes.py`
 * exactly so the two never drift. Non-OK responses are surfaced as a typed
 * `NoteError` whose `kind` lets callers branch on the documented failures — a
 * stale capture (409, the reader tells the user to reload) and an over-cap body
 * (422, the editor flags the length) — without matching on message strings.
 */

/** A note's book citation, mirroring the backend `NoteAnchorView` (NF-10). */
export type NoteAnchor = {
  id: string;
  source_id: string;
  source_title: string;
  anchor: string;
  section_path: string[];
  block_ordinal: number | null;
  start_offset: number | null;
  end_offset: number | null;
  quote_exact: string;
  quote_prefix: string;
  quote_suffix: string;
  status: string;
};

/** The note-detail read model, mirroring the backend `NoteDetailView`. */
export type NoteDetail = {
  id: string;
  title: string;
  body_markdown: string;
  tags: string[];
  anchors: NoteAnchor[];
  created_at: string;
  updated_at: string;
};

/** One row in the notes list, mirroring the backend `NoteSummaryView` (NF-13). */
export type NoteSummary = {
  id: string;
  title: string;
  tags: string[];
  anchor_statuses: string[];
  created_at: string;
  updated_at: string;
};

/** One inbound wikilink for the backlinks panel, mirroring `BacklinkView`. */
export type Backlink = {
  note_id: string;
  title: string;
};

/** The create/update body, mirroring the backend `NoteWriteRequest`. */
export type NoteWrite = {
  title: string;
  body_markdown?: string;
  tags?: string[];
};

/**
 * The highlight-capture body, mirroring the backend `CaptureRequest`. The
 * selection payload (`quote_exact` + 32-char `quote_prefix`/`quote_suffix`
 * context, resolved server-side against the section blocks) rides alongside the
 * new note's fields; an empty `body_markdown` yields a bare highlight.
 */
export type CaptureHighlight = {
  anchor: string;
  quote_exact: string;
  quote_prefix?: string;
  quote_suffix?: string;
  title: string;
  body_markdown?: string;
  tags?: string[];
};

/**
 * The documented failure the caller can branch on. `stale_capture` (409) means
 * the served evidence no longer matches the section (a mid-flight re-ingest) so
 * the reader should reload; `body_too_long` (422) means the note body exceeds the
 * cap so the editor should flag it; every other non-OK response collapses to
 * `unknown`.
 */
export type NoteErrorKind = "stale_capture" | "body_too_long" | "unknown";

/**
 * A non-OK notes response, carrying the mapped `kind` and the backend `detail`
 * (or a readable fallback) as its message. Callers match on `kind`, not the
 * message, so copy changes never break control flow.
 */
export class NoteError extends Error {
  readonly kind: NoteErrorKind;
  readonly status: number;

  constructor(kind: NoteErrorKind, status: number, message: string) {
    super(message);
    this.name = "NoteError";
    this.kind = kind;
    this.status = status;
  }
}

/**
 * Create a whole-Markdown note (201). State-changing, so it carries the
 * session-bound CSRF token in `X-CSRF-Token` (AD-007). An over-cap body surfaces
 * as a `NoteError` with kind `body_too_long` (422).
 */
export async function createNote(
  body: NoteWrite,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<NoteDetail> {
  const res = await fetchImpl("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not create the note.");
  }
  return (await res.json()) as NoteDetail;
}

/**
 * List the caller's notes (newest-edited first), optionally filtered to one tag
 * (matched case-insensitively). Read-only GET, so no CSRF token. On a non-OK
 * response the backend `detail` is surfaced via `NoteError`.
 */
export async function listNotes(
  { tag }: { tag?: string } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<NoteSummary[]> {
  const query = tag !== undefined ? `?tag=${encodeURIComponent(tag)}` : "";
  const res = await fetchImpl(`/api/notes${query}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not load your notes.");
  }
  return (await res.json()) as NoteSummary[];
}

/**
 * Fetch one owned note's detail (200). Read-only GET, so no CSRF token. A missing
 * or non-owned note collapses to a 404 surfaced via `NoteError`.
 */
export async function getNote(
  noteId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<NoteDetail> {
  const res = await fetchImpl(`/api/notes/${noteId}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not load that note.");
  }
  return (await res.json()) as NoteDetail;
}

/**
 * Update an owned note and rewrite its derived indexes (200). State-changing, so
 * it carries the CSRF token in `X-CSRF-Token`. An over-cap body surfaces as a
 * `NoteError` with kind `body_too_long` (422).
 */
export async function updateNote(
  noteId: string,
  body: NoteWrite,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<NoteDetail> {
  const res = await fetchImpl(`/api/notes/${noteId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not save the note.");
  }
  return (await res.json()) as NoteDetail;
}

/**
 * Delete an owned note (204, no body). State-changing, so it carries the CSRF
 * token in `X-CSRF-Token`. A missing or non-owned note collapses to a 404
 * surfaced via `NoteError`.
 */
export async function deleteNote(
  noteId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl(`/api/notes/${noteId}`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not delete the note.");
  }
}

/**
 * Fetch the notes whose wikilinks resolve to an owned note (200). Read-only GET,
 * so no CSRF token. Owner-scoped like `getNote` (missing/non-owned → 404).
 */
export async function getBacklinks(
  noteId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Backlink[]> {
  const res = await fetchImpl(`/api/notes/${noteId}/backlinks`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not load the backlinks.");
  }
  return (await res.json()) as Backlink[];
}

/**
 * Capture a highlight from the reader: create a note + one book anchor atomically
 * (201). State-changing, so it carries the CSRF token in `X-CSRF-Token`. When the
 * served evidence no longer matches the section (a mid-flight re-ingest) the call
 * surfaces a `NoteError` with kind `stale_capture` (409); an over-cap body
 * surfaces kind `body_too_long` (422).
 */
export async function captureHighlight(
  sourceId: string,
  body: CaptureHighlight,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<NoteDetail> {
  const res = await fetchImpl(`/api/sources/${sourceId}/highlights`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await toNoteError(res, "Could not capture the highlight.");
  }
  return (await res.json()) as NoteDetail;
}

/**
 * Build a typed `NoteError` from a non-OK response. The status maps to a `kind`
 * (409 → `stale_capture`, 422 → `body_too_long`, else `unknown`) and the backend
 * `detail` string becomes the message; a 422 detail arrives as a list of
 * validation errors, not a string, so those fall back to the readable message
 * rather than a stringified list (mirroring `toQuizError`).
 */
async function toNoteError(res: Response, fallback: string): Promise<NoteError> {
  const kind: NoteErrorKind =
    res.status === 409
      ? "stale_capture"
      : res.status === 422
        ? "body_too_long"
        : "unknown";
  try {
    const body = (await res.json()) as { detail?: unknown };
    const message = typeof body.detail === "string" ? body.detail : fallback;
    return new NoteError(kind, res.status, message);
  } catch {
    return new NoteError(kind, res.status, fallback);
  }
}
