/**
 * Browser-side questions client (D1, QA-20/QA-21).
 *
 * Thin helper the ask panel uses to POST a question to FastAPI *through the
 * same-origin Next.js proxy* (`/api/...`, ADR-017) — never cross-origin. The
 * HttpOnly session cookie rides along automatically (`credentials:
 * "same-origin"`), so this code never reads or holds the session token. Asking a
 * question is a state-changing request, so it echoes the CSRF token (from
 * `/api/auth/me`) in `X-CSRF-Token` (AD-007), mirroring `sources.ts`.
 *
 * FastAPI remains authoritative for auth, ownership, readiness, and generation;
 * this helper just carries the question in and surfaces the answer/error out.
 */

/** One grounded citation, mirroring the backend `EvidenceView`. */
export type Citation = {
  chunk_id: string;
  source_id: string;
  section_path: string[];
  anchor: string;
  page_span: Record<string, unknown> | null;
  snippet: string;
  score: number;
};

/**
 * A cited answer or the explicit not-found outcome, mirroring the backend
 * `AnswerResponse`. `answer` is `""` and `citations` is empty for
 * `not_found_in_source`; `retrieval`/`model` diagnostics are present on both
 * outcomes (QA-04).
 */
export type AnswerView = {
  answer_status: "answered" | "not_found_in_source";
  answer: string;
  citations: Citation[];
  retrieval: { strategy: string; evidence_count: number };
  model: string;
};

/**
 * Ask a question against a ready source and get a grounded, cited answer (or the
 * explicit not-found outcome). State-changing, so it carries the session-bound
 * CSRF token in `X-CSRF-Token` (AD-007); the caller passes it in (read from
 * `/api/auth/me`), same as `uploadSource`. The `question` trimmed body is a JSON
 * object. On a non-OK response (409 not-ready, 429 throttled, 502 generation
 * failure, …) the backend `detail` is surfaced via `toQuestionError`.
 */
export async function askQuestion(
  sourceId: string,
  question: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AnswerView> {
  const res = await fetchImpl(`/api/sources/${sourceId}/questions`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw await toQuestionError(res, "Could not get an answer.");
  }
  return (await res.json()) as AnswerView;
}

/**
 * Build an Error from a non-OK response, preferring the backend's detail.
 * FastAPI validation errors (422) carry `detail` as a list of error objects, not
 * a string — those fall back to the readable message instead of rendering a
 * stringified list (QA-20).
 */
async function toQuestionError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
