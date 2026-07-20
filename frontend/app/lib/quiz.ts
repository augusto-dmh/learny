/**
 * Browser-side quiz + review client (E1, QUIZ-21).
 *
 * Thin helpers the library and review screens use to drive quiz decks and
 * spaced-repetition reviews against FastAPI *through the same-origin Next.js
 * proxy* (`/api/...`, ADR-017) — never cross-origin. The HttpOnly session cookie
 * rides along automatically (`credentials: "same-origin"`), so this code never
 * reads or holds the session token. The two reads (overview, due queue) carry no
 * token; the state-changing POSTs (generate deck, submit review) echo the CSRF
 * token (from `/api/auth/me`) in `X-CSRF-Token` (AD-007), mirroring `teaching.ts`.
 *
 * FastAPI remains authoritative for auth, ownership, readiness, grounding, and
 * FSRS scheduling; these helpers just carry inputs in and surface the
 * overview/queue/scheduling/error out. The response types mirror the backend
 * views in `web/quiz.py` exactly so the two never drift.
 */

/** A deck-generation job's public state, mirroring the backend `QuizJobView`. */
export type QuizJob = {
  id: string;
  status: string;
  attempts: number;
  generated_count: number;
  discarded_count: number;
  failed_sections: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};

/** One item in the per-source overview, mirroring the backend `QuizItemSummaryView`. */
export type QuizItemSummary = {
  id: string;
  item_type: string;
  question: string;
  status: string;
  due: string | null;
};

/** The per-source overview, mirroring the backend `QuizOverviewView` — the deck-poll target. */
export type QuizOverview = {
  items: QuizItemSummary[];
  counts_by_status: Record<string, number>;
  due_count: number;
  latest_job: QuizJob | null;
};

/** A due card's citation snapshot, mirroring the backend `CitationView`. */
export type QuizCitation = {
  section_path: string[];
  anchor: string;
  source_excerpt: string;
};

/**
 * The origin note of a card made at a passage, mirroring the backend
 * `CardProvenanceView`. Read by join, so the title is always the note's current
 * one rather than a copy that drifts after a rename.
 */
export type CardProvenance = {
  note_id: string;
  note_title: string;
};

/**
 * One due review card, mirroring the backend `DueItemView`. Carries the full
 * card — question, answer, and citation — because reveal is a client-side act in
 * the self-grade flow (no server round-trip to reveal).
 *
 * `provenance` is the origin note of a card the student made at a passage
 * (CAP-16). It is explicitly `null` for a deck-generated card and for one whose
 * origin note has since been deleted — the card outlives its note, so review must
 * render either way.
 */
export type DueItem = {
  id: string;
  source_id: string;
  source_title: string;
  item_type: string;
  question: string;
  answer: string;
  citation: QuizCitation;
  provenance: CardProvenance | null;
  status: string;
  due: string;
};

/** The due queue response, mirroring the backend `DueQueueView`. */
export type DueQueue = {
  items: DueItem[];
  total_due: number;
};

/** The updated scheduling snapshot returned after a review (backend `SchedulingView`). */
export type Scheduling = {
  state: number;
  step: number | null;
  stability: number | null;
  difficulty: number | null;
  due: string;
  last_review: string | null;
};

/**
 * Fetch a source's quiz overview: items + per-status counts + due count + latest
 * deck job. Read-only GET, so no CSRF token; the HttpOnly session cookie rides
 * along automatically. This is the deck-progress polling target. On a non-OK
 * response (401 unauthenticated, 404 missing/non-owned) the backend `detail` is
 * surfaced via `toQuizError`.
 */
export async function getQuizOverview(
  sourceId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<QuizOverview> {
  const res = await fetchImpl(`/api/sources/${sourceId}/quiz`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toQuizError(res, "Could not load the quiz overview.");
  }
  return (await res.json()) as QuizOverview;
}

/**
 * Start deck generation for a ready source and get the queued job (202).
 * State-changing, so it carries the session-bound CSRF token in `X-CSRF-Token`
 * (AD-007); the caller passes it in (read from `/api/auth/me`). On a non-OK
 * response (404 missing/non-owned, 409 not-ready/already-running, 429 throttled,
 * 502 enqueue failure) the backend `detail` is surfaced via `toQuizError`.
 */
export async function generateDeck(
  sourceId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<QuizJob> {
  const res = await fetchImpl(`/api/sources/${sourceId}/quiz/deck`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await toQuizError(res, "Could not start quiz deck generation.");
  }
  return (await res.json()) as QuizJob;
}

/**
 * Fetch the caller's due review queue across their sources (optionally filtered
 * to one source, optionally capped by `limit`). Read-only GET, so no CSRF token.
 * On a non-OK response (401 unauthenticated, 422 over-limit) the backend `detail`
 * is surfaced via `toQuizError`.
 */
export async function getDueReviews(
  { sourceId, limit }: { sourceId?: string; limit?: number } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<DueQueue> {
  const params = new URLSearchParams();
  if (sourceId !== undefined) {
    params.set("source_id", sourceId);
  }
  if (limit !== undefined) {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  const res = await fetchImpl(`/api/reviews/due${query ? `?${query}` : ""}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toQuizError(res, "Could not load your due reviews.");
  }
  return (await res.json()) as DueQueue;
}

/**
 * Submit a 4-button self-grade for one active item and get its updated FSRS
 * scheduling (200). State-changing, so it carries the session-bound CSRF token in
 * `X-CSRF-Token` (AD-007). The optional `review_duration_ms` is the client-timed
 * question-to-grade duration. On a non-OK response (404 missing/non-owned, 409
 * stale/orphaned, 422 rating bounds, 429 throttled) the backend `detail` is
 * surfaced via `toQuizError`.
 */
export async function submitReview(
  itemId: string,
  body: { rating: number; review_duration_ms?: number },
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Scheduling> {
  const res = await fetchImpl(`/api/quiz-items/${itemId}/reviews`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await toQuizError(res, "Could not submit your review.");
  }
  return (await res.json()) as Scheduling;
}

/**
 * Build the same-origin URL for a source's Anki `.apkg` export. This is a plain
 * navigable/downloadable link (no fetch, no token) — the browser carries the
 * HttpOnly session cookie automatically and FastAPI authorizes ownership.
 */
export function quizExportUrl(sourceId: string): string {
  return `/api/sources/${sourceId}/quiz/export`;
}

/**
 * Build an Error from a non-OK response, preferring the backend's detail.
 * FastAPI validation errors (422) carry `detail` as a list of error objects, not
 * a string — those fall back to the readable message instead of rendering a
 * stringified list, mirroring `teaching.ts`.
 */
async function toQuizError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
