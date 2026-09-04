/**
 * Accept the closed tutor restatement as one review card.
 *
 * This is not the highlight `acceptCard` path: the conversation is the identity,
 * and the server mints the frozen question plus `tutor_check_text`. Suggesting
 * cards is a different product and must not be called from this flow.
 */

export class TutorCardError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "TutorCardError";
    this.status = status;
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
    throw new TutorCardError(res.status, "Could not save this review card.");
  }
}
