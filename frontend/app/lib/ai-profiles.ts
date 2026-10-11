/**
 * Browser-side AI-profile client — the learner's generation-profile choice.
 *
 * Two resources drive the account page's "AI profile" section: the deployment's
 * *catalog* of selectable profiles (what the operator declares, with honest
 * learner-facing copy) and the caller's single stored *choice*. These helpers
 * talk to both *through the same-origin Next.js proxy* (`/api/...`, ADR-017) —
 * never cross-origin. The HttpOnly session cookie rides along automatically
 * (`credentials: "same-origin"`), so this code never reads or holds the session
 * token; the mutating calls echo the session-bound CSRF token in
 * `X-CSRF-Token`.
 *
 * FastAPI remains authoritative: it validates a PUT against the currently
 * declared registry (an unknown id is a 422 whose detail names the problem and
 * persists nothing), it rejects unauthenticated reads, and DELETE is idempotent.
 * The stored choice is returned exactly as stored — an id the operator renamed
 * or removed is never rewritten here; callers decide how a stale id renders
 * (the account selector treats anything absent from the catalog as unset).
 *
 * Failures raise `AiProfileRequestError`, an `ApiError` that keeps the status
 * that produced it, so a caller can tell an unauthenticated probe (401) or an
 * unknown id (422) from a transient failure. The backend `detail` rides along as
 * data; the learner reads catalog copy chosen from the operation and status.
 */

import { ApiError, readDetail, type ApiOperation } from "./errors";

/** How a profile grounds its answers in the book's evidence. */
export type ProfileGrounding = "verified-spans" | "prompt-cited" | "none";

/**
 * One selectable profile of the deployment's catalog, mirroring the backend's
 * learner-facing projection. It carries exactly what a learner may see —
 * identity, honest copy, grounding mechanism, per-mode eligibility — and none
 * of the operator-side declaration (adapter kind, key names, prices).
 */
export type LearnerProfile = {
  id: string;
  /** Operator-curated display name; falls back to the id when unset. */
  display_name: string;
  /** What this profile trades away; empty means the UI hides the copy line. */
  description: string;
  grounding: ProfileGrounding;
  ask_enabled: boolean;
  teach_enabled: boolean;
};

/** The choice resource: the stored id, or null when nothing is set. */
export type AiProfileChoice = {
  profile_id: string | null;
};

/**
 * A failed call, carrying the operation, the status that produced it and the
 * backend `detail` as data. Callers key off `status` to tell an expired session
 * (401) or a refused id (422) from anything else.
 */
export class AiProfileRequestError extends ApiError {
  declare readonly status: number;

  constructor(operation: ApiOperation, status: number, detail: string | null = null) {
    super(operation, status, detail);
    this.name = "AiProfileRequestError";
  }
}

/**
 * List the deployment's selectable AI profiles in registry order. Empty when
 * the deployment declares nothing selectable — the account selector renders
 * nothing at all in that state rather than a one-row dead control.
 */
export async function listAiProfiles(
  fetchImpl: typeof fetch = fetch,
): Promise<LearnerProfile[]> {
  const res = await fetchImpl("/api/ai/profiles", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toAiProfileError(res, "aiProfilesList");
  }
  return (await res.json()) as LearnerProfile[];
}

/** Read the caller's stored choice (as stored; may name a stale id). */
export async function getAiProfileChoice(
  fetchImpl: typeof fetch = fetch,
): Promise<AiProfileChoice> {
  const res = await fetchImpl("/api/me/ai-profile", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toAiProfileError(res, "aiProfileGet");
  }
  return (await res.json()) as AiProfileChoice;
}

/**
 * Store the caller's choice; a re-put replaces it. The backend refuses an id
 * nothing currently declares with a 422 whose detail names the problem.
 */
export async function putAiProfileChoice(
  profileId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AiProfileChoice> {
  const res = await fetchImpl("/api/me/ai-profile", {
    method: "PUT",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!res.ok) {
    throw await toAiProfileError(res, "aiProfileSave");
  }
  return (await res.json()) as AiProfileChoice;
}

/**
 * Unset the caller's choice, returning serving to the operator default.
 * Idempotent: 204 even when nothing was set.
 */
export async function deleteAiProfileChoice(
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl("/api/me/ai-profile", {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await toAiProfileError(res, "aiProfileReset");
  }
}

/** Build the typed error for a non-OK response to `operation`. */
async function toAiProfileError(
  res: Response,
  operation: ApiOperation,
): Promise<AiProfileRequestError> {
  return new AiProfileRequestError(operation, res.status, await readDetail(res));
}
