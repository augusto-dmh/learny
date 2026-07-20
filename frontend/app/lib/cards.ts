/**
 * Browser-side cards client (CAP-01, CAP-05..08).
 *
 * Thin helpers the reader's capture flow uses to turn a highlighted passage into a
 * scheduled review card, driven against FastAPI *through the same-origin Next.js
 * proxy* (`/api/...`, ADR-017) — never cross-origin. The HttpOnly session cookie
 * rides along automatically (`credentials: "same-origin"`), so this code never
 * reads or holds the session token. Both calls are state-changing writes, so each
 * echoes the CSRF token (from `/api/auth/me`) in `X-CSRF-Token` (AD-007),
 * mirroring `notes.ts`.
 *
 * FastAPI remains authoritative for auth, ownership, the groundedness QC that gates
 * generated candidates, the text bounds, and FSRS scheduling; these helpers just
 * carry inputs in and surface the suggestions/card/error out. The response types
 * mirror the backend views in `web/cards.py` exactly so the two never drift.
 *
 * Non-OK responses surface as a typed `CardError` whose `kind` lets callers branch
 * on the documented failures without matching on message strings — following the
 * `NoteError` convention in `notes.ts`, not the bare `Error` that `quiz.ts` throws.
 */

/** One ephemeral card candidate, mirroring the backend `CardSuggestionView`. */
export type CardSuggestion = {
  item_type: string;
  question: string;
  answer: string;
  anchor_quote: string;
};

/** A card's citation snapshot, mirroring the backend `CardCitationView`. */
export type CardCitation = {
  section_path: string[];
  anchor: string;
  source_excerpt: string;
};

/**
 * A persisted card, mirroring the backend `CardView`. `id` is the creation-minted
 * stable identity a `highlight` card keeps across every later edit, and
 * `note_anchor_id` is the typed provenance back to the highlight it came from — it
 * goes `null` when that highlight's note is deleted while the card survives.
 */
export type Card = {
  id: string;
  source_id: string;
  origin: string;
  note_anchor_id: string | null;
  item_type: string;
  question: string;
  answer: string;
  citation: CardCitation;
  status: string;
  created_at: string;
  updated_at: string;
};

/** The accept body, mirroring the backend `AcceptCardRequest`. */
export type AcceptCardBody = {
  note_anchor_id: string;
  item_type: string;
  question: string;
  answer: string;
};

/**
 * The documented failures a caller can branch on. `stale_capture` (409) means the
 * passage changed under the highlight so the reader should reload; `invalid` (422)
 * means the submitted text is empty or over the length bound; every other non-OK
 * response collapses to `unknown`.
 *
 * The backend also exposes `PATCH /api/quiz-items/{id}` for rewording an accepted
 * card, which answers 409 for a deck-origin card. No surface in this cycle edits a
 * saved card, so no client for that route ships here — it arrives with the note-
 * derived cards that need it, rather than sitting unused in the meantime.
 */
export type CardErrorKind = "stale_capture" | "invalid" | "unknown";

/**
 * A non-OK cards response, carrying the mapped `kind` and the backend `detail` (or
 * a readable fallback) as its message. Callers match on `kind`, not the message, so
 * copy changes never break control flow.
 */
export class CardError extends Error {
  readonly kind: CardErrorKind;
  readonly status: number;

  constructor(kind: CardErrorKind, status: number, message: string) {
    super(message);
    this.name = "CardError";
    this.kind = kind;
    this.status = status;
  }
}

/**
 * Ask for card candidates scoped to one owned highlight (200). Nothing is persisted
 * by this call — the candidates live in component state until the student accepts
 * one, so a student who never accepts leaves no rows behind.
 *
 * An empty list is a normal outcome ("no cards for this passage"), not an error. A
 * passage that changed under the highlight surfaces as a `CardError` with kind
 * `stale_capture` (409).
 */
export async function suggestCards(
  sourceId: string,
  noteAnchorId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CardSuggestion[]> {
  const res = await fetchImpl(`/api/sources/${sourceId}/cards/suggestions`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ note_anchor_id: noteAnchorId }),
  });
  if (!res.ok) {
    throw await toCardError(res, "Could not suggest cards for this passage.");
  }
  const body = (await res.json()) as { suggestions: CardSuggestion[] };
  return body.suggestions;
}

/**
 * Accept one candidate as a card, scheduled due immediately (201). The text is
 * whatever the student accepted — the candidate verbatim or their own edit of it.
 *
 * Accepting the same text from the same highlight twice is idempotent server-side:
 * the second call answers 200 with the *existing* card instead of 201, so a double
 * submit yields one card and neither status is a failure. Empty or over-long text
 * surfaces as a `CardError` with kind `invalid` (422).
 */
export async function acceptCard(
  sourceId: string,
  body: AcceptCardBody,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Card> {
  const res = await fetchImpl(`/api/sources/${sourceId}/cards`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await toCardError(res, "Could not save this card.");
  }
  return (await res.json()) as Card;
}

/**
 * Build a typed `CardError` from a non-OK response. 409 maps to `stale_capture`
 * (the passage moved under the highlight) and 422 to `invalid`. The backend
 * `detail` string becomes the message; a 422 detail arrives as a list of validation
 * errors, not a string, so those fall back to the readable message rather than a
 * stringified list.
 */
async function toCardError(res: Response, fallback: string): Promise<CardError> {
  const kind: CardErrorKind =
    res.status === 409 ? "stale_capture" : res.status === 422 ? "invalid" : "unknown";
  try {
    const body = (await res.json()) as { detail?: unknown };
    const message = typeof body.detail === "string" ? body.detail : fallback;
    return new CardError(kind, res.status, message);
  } catch {
    return new CardError(kind, res.status, fallback);
  }
}
