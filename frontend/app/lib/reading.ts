/**
 * Browser-side reading client (RD-01/07/28).
 *
 * Thin helpers the chapter-flow reader uses to drive the reader routes against
 * FastAPI *through the same-origin Next.js proxy* (`/api/...`, ADR-017) — never
 * cross-origin. The HttpOnly session cookie rides along automatically
 * (`credentials: "same-origin"`), so this code never reads or holds the session
 * token. The reads (chapter, highlights) carry no CSRF token; the position write
 * echoes the CSRF token (from `/api/auth/me`) in `X-CSRF-Token` (AD-007),
 * mirroring `notes.ts`.
 *
 * FastAPI stays authoritative for auth, ownership, anchor resolution, and the
 * server-computed percent. The response types mirror the backend views in
 * `web/sources.py` / `web/notes.py` exactly so the two never drift. A chapter
 * anchor that matches nothing (or a non-owned source) is a 404 the reader renders
 * as a not-found state, so `getChapter` returns a typed `not_found` rather than
 * throwing; other non-OK responses throw. The anchor carries reserved characters
 * (`/`, `#`), so it is `encodeURIComponent`-encoded exactly once — and omitted
 * entirely when resuming, so the server picks the stored position's chapter.
 */

/** Words-per-minute for the minutes-left estimate (AD-126; mirrors the backend). */
export const WORDS_PER_MINUTE = 220;

/** One section of the chapter flow, mirroring the backend `ChapterSectionView`. */
export type ChapterSectionView = {
  anchor: string;
  title: string;
  section_path: string[];
  markdown: string;
  word_count: number;
};

/** The stored reading position, mirroring the backend `ReadingPositionView`. */
export type ReadingPositionView = {
  anchor: string;
  percent: number;
  updated_at: string;
};

/** A whole chapter for the reader, mirroring the backend `ChapterView`. */
export type ChapterView = {
  chapter_title: string;
  chapter_anchor: string;
  chapter_index: number;
  chapter_count: number;
  prev_anchor: string | null;
  next_anchor: string | null;
  words_before_chapter: number;
  chapter_word_count: number;
  total_word_count: number;
  sections: ChapterSectionView[];
  reading_position: ReadingPositionView | null;
};

/**
 * One of the caller's highlights, mirroring the backend `SourceHighlightView`.
 *
 * `note_title` and `has_body` let the margin rail label an entry without a second
 * round trip (CAP-19): a highlight the student wrote on shows its note's title,
 * while a bare highlight is identified by its own quote snapshot.
 */
export type SourceHighlightView = {
  note_id: string;
  note_title: string;
  has_body: boolean;
  anchor: string;
  quote_exact: string;
  quote_prefix: string;
  quote_suffix: string;
  status: "active" | "stale" | "orphaned";
};

/** The chapter either resolved, or its anchor matched nothing (404). */
export type ChapterResult =
  | { status: "found"; chapter: ChapterView }
  | { status: "not_found" };

/**
 * Fetch a chapter by anchor, or resume the stored position when `anchor` is null
 * (the query is omitted so the server picks the stored — or first — chapter).
 * Returns `{status: "not_found"}` on 404 (the reader's not-found state); throws a
 * readable error on any other non-OK response (e.g. 401 unauthenticated).
 */
export async function getChapter(
  sourceId: string,
  anchor: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<ChapterResult> {
  const query = anchor !== null ? `?anchor=${encodeURIComponent(anchor)}` : "";
  const res = await fetchImpl(`/api/sources/${sourceId}/chapter${query}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (res.status === 404) {
    return { status: "not_found" };
  }
  if (!res.ok) {
    throw await toReadingError(res, "Could not load that chapter.");
  }
  return { status: "found", chapter: (await res.json()) as ChapterView };
}

/**
 * Store the caller's reading position for a source (200). State-changing, so it
 * carries the session-bound CSRF token in `X-CSRF-Token` (AD-007). Throws on any
 * non-OK response — the reader treats the write as fire-and-forget and retries on
 * the next scroll-idle (RD-13), so the caller catches and swallows.
 */
export async function saveReadingPosition(
  sourceId: string,
  anchor: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ReadingPositionView> {
  const res = await fetchImpl(`/api/sources/${sourceId}/reading-position`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ anchor }),
  });
  if (!res.ok) {
    throw await toReadingError(res, "Could not save your reading position.");
  }
  return (await res.json()) as ReadingPositionView;
}

/**
 * List the caller's highlights on a source (200). Read-only GET, so no CSRF
 * token. A missing or non-owned source collapses to a 404 surfaced as a thrown
 * error; the reader paints the `active` quotes it can match (RD-29).
 */
export async function listHighlights(
  sourceId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SourceHighlightView[]> {
  const res = await fetchImpl(`/api/sources/${sourceId}/highlights`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toReadingError(res, "Could not load your highlights.");
  }
  return (await res.json()) as SourceHighlightView[];
}

/**
 * Minutes left to read `words` at `wpm` (220 by default, AD-126), rounded up so a
 * partial minute still shows. Floors at zero for a fully-read (or over-read)
 * chapter, so the progress display never goes negative.
 */
export function minutesLeft(words: number, wpm: number = WORDS_PER_MINUTE): number {
  if (words <= 0) {
    return 0;
  }
  return Math.ceil(words / wpm);
}

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toReadingError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
