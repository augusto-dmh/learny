/**
 * Accept the closed tutor restatement as one review card.
 *
 * This is not the highlight `acceptCard` path: the conversation is the identity,
 * and the server mints the frozen question plus `tutor_check_text`. Suggesting
 * cards is a different product and must not be called from this flow.
 */

import { ApiError, readDetail } from "./errors";

/** A refused tutor-card accept: an `ApiError` whose `status` callers branch on. */
export class TutorCardError extends ApiError {
  declare readonly status: number;

  constructor(status: number, detail: string | null = null) {
    super("tutorCardSave", status, detail);
    this.name = "TutorCardError";
  }
}

export async function acceptTutorCard(
  conversationId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl(`/api/conversations/${conversationId}/tutor-card`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw new TutorCardError(res.status, await readDetail(res));
  }
}
