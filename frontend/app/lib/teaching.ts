/**
 * Browser-side teaching-sessions client (E1, TEACH-22).
 *
 * Thin helpers the teach panel uses to drive teaching sessions against FastAPI
 * *through the same-origin Next.js proxy* (`/api/...`, ADR-017) — never
 * cross-origin. The HttpOnly session cookie rides along automatically
 * (`credentials: "same-origin"`), so this code never reads or holds the session
 * token. Starting a session and posting a turn are state-changing, so they echo
 * the CSRF token (from `/api/auth/me`) in `X-CSRF-Token` (AD-007), mirroring
 * `questions.ts`; the two reads carry no token.
 *
 * FastAPI remains authoritative for auth, ownership, readiness, target scoping,
 * and generation; these helpers just carry inputs in and surface the
 * session/turn/error out.
 */

import { type Citation } from "./questions";

/** The session's target section snapshot, mirroring the backend `TargetView`. */
export type TeachingTarget = {
  anchor: string;
  section_path: string[];
  title: string;
};

/** A started/created session, mirroring the backend `SessionView`. */
export type TeachingSessionView = {
  id: string;
  source_id: string;
  target: TeachingTarget;
  created_at: string;
};

/**
 * One cited teaching turn, mirroring the backend `TurnView`. `text` is `""` and
 * `citations` is empty for `not_found_in_source`; `model`/`evidence_count`
 * diagnostics are present on both outcomes (TEACH-14/24). Citations reuse the
 * retrieval `Citation` shape.
 */
export type TeachingTurnView = {
  turn_index: number;
  message: string;
  answer_status: "answered" | "not_found_in_source";
  text: string;
  citations: Citation[];
  evidence_count: number;
  model: string;
  created_at: string;
};

/**
 * A session with its full ordered conversation, mirroring the backend
 * `SessionDetailView`: `turns` are ordered by `turn_index` ascending, each with
 * its citation snapshots (TEACH-05/20).
 */
export type TeachingSessionDetail = TeachingSessionView & {
  turns: TeachingTurnView[];
};

/** A per-source session summary for the resume list (backend `SessionSummaryView`). */
export type TeachingSessionSummary = {
  id: string;
  target: TeachingTarget;
  created_at: string;
  turn_count: number;
};

/**
 * Start a teaching session anchored to a section of a ready source.
 * State-changing, so it carries the session-bound CSRF token in `X-CSRF-Token`
 * (AD-007); the caller passes it in (read from `/api/auth/me`), same as
 * `askQuestion`. On a non-OK response (404 not-found, 409 not-ready, 422 unknown
 * target, 429 throttled) the backend `detail` is surfaced via `toTeachingError`.
 */
export async function startTeachingSession(
  sourceId: string,
  targetAnchor: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TeachingSessionView> {
  const res = await fetchImpl("/api/teaching-sessions", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ source_id: sourceId, target_anchor: targetAnchor }),
  });
  if (!res.ok) {
    throw await toTeachingError(res, "Could not start the session.");
  }
  return (await res.json()) as TeachingSessionView;
}

/**
 * Fetch one owned session with its full ordered, cited conversation. Read-only
 * GET, so no CSRF token; the HttpOnly session cookie rides along automatically.
 * Non-OK responses (e.g. 404 missing/non-owned) surface the backend `detail`.
 */
export async function getTeachingSession(
  sessionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TeachingSessionDetail> {
  const res = await fetchImpl(`/api/teaching-sessions/${sessionId}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toTeachingError(res, "Could not load that session.");
  }
  return (await res.json()) as TeachingSessionDetail;
}

/**
 * List a source's teaching sessions (newest first), or `[]` when it has none.
 * Read-only GET, so no CSRF token. Non-OK responses (e.g. 404 missing/non-owned)
 * surface the backend `detail`.
 */
export async function listTeachingSessions(
  sourceId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TeachingSessionSummary[]> {
  const res = await fetchImpl(`/api/sources/${sourceId}/teaching-sessions`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toTeachingError(res, "Could not load previous sessions.");
  }
  return (await res.json()) as TeachingSessionSummary[];
}

/**
 * Send a message in a session and get a cited teaching turn (or the explicit
 * not-found outcome). State-changing, so it carries the session-bound CSRF token
 * in `X-CSRF-Token` (AD-007). On a non-OK response (404, 409 not-ready/
 * target-gone/index-race, 422 bounds, 429 throttled, 502 generation failure) the
 * backend `detail` is surfaced via `toTeachingError`.
 */
export async function postTeachingTurn(
  sessionId: string,
  message: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TeachingTurnView> {
  const res = await fetchImpl(`/api/teaching-sessions/${sessionId}/turns`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    throw await toTeachingError(res, "Could not send your message.");
  }
  return (await res.json()) as TeachingTurnView;
}

/**
 * Build an Error from a non-OK response, preferring the backend's detail.
 * FastAPI validation errors (422) carry `detail` as a list of error objects, not
 * a string — those fall back to the readable message instead of rendering a
 * stringified list, mirroring `questions.ts`.
 */
async function toTeachingError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
