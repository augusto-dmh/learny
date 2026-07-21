/**
 * Browser-side study + continue-reading client (RFC-004 Cycle E, HOME-01/09/11).
 *
 * Thin helpers the Home surface uses to read the adherence rollup and the
 * continue-reading hero from FastAPI *through the same-origin Next.js proxy*
 * (`/api/...`, ADR-017) — never cross-origin. The HttpOnly session cookie rides
 * along automatically (`credentials: "same-origin"`), so this code never reads or
 * holds the session token. Both are read-only GETs, so they carry no CSRF token.
 *
 * The day boundary is user-local: `getStudyDays` echoes the caller's IANA zone in
 * `X-Client-Timezone` so the window ends at their local today (HOME-09/11). The
 * zone comes from `clientTimezone()`, which the reading-position and
 * review-submission writers reuse to date their rollups the same way. When the
 * zone cannot be resolved the header is simply omitted — never sent as the string
 * `"undefined"` — and the backend falls back to UTC (AD-152, HOME-09).
 *
 * FastAPI stays authoritative for auth, user-scoping, and the read-time
 * `studied_last_14`. The response types mirror the backend views in `web/study.py`
 * exactly so the two never drift.
 */

/** The tz header the day boundary rides on (HOME-09). */
const CLIENT_TIMEZONE_HEADER = "X-Client-Timezone";

/** One user-local day of activity, mirroring the backend `StudyDayView`. */
export type StudyDayView = {
  day: string;
  reviews_count: number;
  reading_updates: number;
};

/** The adherence read model, mirroring the backend `StudySummaryView`. */
export type StudySummaryView = {
  days: StudyDayView[];
  studied_last_14: number;
};

/** The continue-reading hero, mirroring the backend `ContinueReadingView`. */
export type ContinueReadingView = {
  source_id: string;
  source_title: string;
  chapter_title: string;
  percent: number;
  updated_at: string;
};

/**
 * The caller's IANA time zone from the browser, or `undefined` when it cannot be
 * resolved (AD-152). Callers attach it as `X-Client-Timezone` only when defined,
 * so an unavailable `Intl` degrades to the server's UTC fallback rather than
 * sending a bogus zone. Never throws.
 */
export function clientTimezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/**
 * Fetch the caller's most-recent reading position as the Home hero, or `null`
 * when they have no positions yet (200 empty shape → the hero's pick-a-book
 * state, HOME-02). Read-only GET, so no CSRF token. Throws a readable error on a
 * non-OK response (e.g. 401 unauthenticated) so the hero can show its own error.
 */
export async function getContinueReading(
  fetchImpl: typeof fetch = fetch,
): Promise<ContinueReadingView | null> {
  const res = await fetchImpl("/api/reading/continue", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toStudyError(res, "Could not load your reading progress.");
  }
  return (await res.json()) as ContinueReadingView | null;
}

/**
 * Fetch the caller's study-day window plus `studied_last_14` (HOME-11). The
 * optional `window` (days) is passed through to the endpoint; when omitted the
 * server applies its 84-day default. Echoes `X-Client-Timezone` so the window
 * ends at the caller's local today, omitting it when the zone is unavailable
 * (HOME-09). Read-only GET, so no CSRF token. Throws a readable error on a
 * non-OK response.
 */
export async function getStudyDays(
  window?: number,
  fetchImpl: typeof fetch = fetch,
): Promise<StudySummaryView> {
  const query = window !== undefined ? `?window=${window}` : "";
  const headers: Record<string, string> = {};
  const tz = clientTimezone();
  if (tz) {
    headers[CLIENT_TIMEZONE_HEADER] = tz;
  }
  const res = await fetchImpl(`/api/study/days${query}`, {
    method: "GET",
    credentials: "same-origin",
    headers,
  });
  if (!res.ok) {
    throw await toStudyError(res, "Could not load your study activity.");
  }
  return (await res.json()) as StudySummaryView;
}

/**
 * Build an Error from a non-OK response, preferring the backend's detail. A
 * non-string detail (e.g. a 422 validation list) falls back to the readable
 * message, mirroring `quiz.ts`.
 */
async function toStudyError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
