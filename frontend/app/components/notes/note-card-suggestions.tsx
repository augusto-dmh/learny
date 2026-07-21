"use client";

/**
 * Note promotion panel (NL-08, NL-15) — the note→review flow on a note's page.
 *
 * "Add to review" generates card candidates grounded in the note body (the note IS
 * the source) and raises them as chips the reader resolves one at a time: Accept
 * promotes it to a scheduled `note` card, Edit rewrites the question/answer inline
 * so the *edited* text is what is promoted (AD-138), and Discard drops it
 * client-side without a request. Nothing is persisted until an Accept (AD-134),
 * mirroring the highlight capture flow.
 *
 * Re-promotion is the explicit path to new cards (AD-144): the panel keeps an honest
 * count of the note's review cards across suggest cycles — an idempotent re-accept
 * of identical text returns the same card (NL-15 dedup) and never inflates the
 * count. An empty candidate list reads as "nothing could be grounded" (a QC outcome,
 * not an error); a generation failure reads as a retryable error.
 *
 * FastAPI stays authoritative for ownership, the groundedness QC, the text bounds,
 * and FSRS scheduling — this panel only carries inputs in and surfaces the
 * candidates/card/error out.
 */

import { useState } from "react";

import {
  acceptNoteCard,
  suggestNoteCards,
  type Card,
  type CardSuggestion,
} from "@/app/lib/cards";
import { Button } from "@/components/ui/button";

export function NoteCardSuggestions({
  noteId,
  csrf,
}: {
  noteId: string;
  csrf: string;
}) {
  // `null` until the reader first asks; then the batch (possibly empty after QC).
  const [suggestions, setSuggestions] = useState<CardSuggestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The distinct cards this note has in review, by minted id. A re-accept of the
  // same text returns the same id, so the size stays honest across re-promotion.
  const [cardIds, setCardIds] = useState<Set<string>>(new Set());
  // Whether the most recent accept resolved to an already-existing card (200),
  // so the panel can say the dedup happened rather than silently no-op.
  const [lastExisting, setLastExisting] = useState(false);

  async function handleSuggest() {
    setLoading(true);
    setError(null);
    setLastExisting(false);
    try {
      setSuggestions(await suggestNoteCards(noteId, csrf));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not suggest cards for this note.",
      );
      setSuggestions(null);
    } finally {
      setLoading(false);
    }
  }

  function handleAccepted(card: Card, created: boolean) {
    setCardIds((prev) => {
      const next = new Set(prev);
      next.add(card.id);
      return next;
    });
    setLastExisting(!created);
  }

  const count = cardIds.size;

  return (
    <section aria-label="Add to review" className="space-y-3">
      <div className="flex items-center gap-3">
        <Button type="button" onClick={() => void handleSuggest()} disabled={loading}>
          {loading ? "Generating…" : "Add to review"}
        </Button>
        {count > 0 ? (
          <span data-testid="note-card-count" className="text-sm text-muted-foreground">
            {count} {count === 1 ? "card" : "cards"} in review from this note
          </span>
        ) : null}
      </div>

      {lastExisting ? (
        <p className="text-xs text-muted-foreground">
          That card is already in review — re-promoting the same text never duplicates it.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {suggestions !== null && !loading && !error ? (
        suggestions.length === 0 ? (
          // A generation that grounded nothing is an outcome, not an error: there is
          // simply nothing here worth remembering.
          <p className="text-sm text-muted-foreground">
            No cards could be grounded in this note.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {suggestions.map((suggestion, index) => (
              <NoteSuggestionChip
                key={`${suggestion.question}-${index}`}
                noteId={noteId}
                csrf={csrf}
                suggestion={suggestion}
                onAccepted={handleAccepted}
              />
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}

/**
 * One candidate. Holds its own draft text, pending flag, and error so the three
 * verbs are independent per chip. Accept promotes the draft — the generated text
 * until the reader edits it, their own words afterwards. Discard is deliberately
 * local: it calls nothing, because an un-promoted candidate has nothing to delete.
 * A resolved chip removes itself; a failed one stays to be retried in place.
 */
function NoteSuggestionChip({
  noteId,
  csrf,
  suggestion,
  onAccepted,
}: {
  noteId: string;
  csrf: string;
  suggestion: CardSuggestion;
  onAccepted: (card: Card, created: boolean) => void;
}) {
  const [resolved, setResolved] = useState(false);
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(suggestion.question);
  const [answer, setAnswer] = useState(suggestion.answer);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAccept() {
    setPending(true);
    setError(null);
    try {
      // Both 201 (newly promoted) and 200 (an idempotent re-promote of the same
      // text) resolve here — the count dedups on the returned id, so neither is a
      // failure to retry.
      const { card, created } = await acceptNoteCard(
        noteId,
        { item_type: suggestion.item_type, question, answer },
        csrf,
      );
      onAccepted(card, created);
      setResolved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add this card to review.");
      setPending(false);
    }
  }

  if (resolved) {
    return null;
  }

  return (
    <li
      data-testid="note-card-suggestion"
      className="flex flex-col gap-1 rounded-md border p-2"
    >
      {editing ? (
        <>
          <textarea
            aria-label="Question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="w-full rounded-sm border bg-background p-1 text-sm"
            rows={2}
          />
          <textarea
            aria-label="Answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            className="w-full rounded-sm border bg-background p-1 text-sm"
            rows={2}
          />
        </>
      ) : (
        <>
          <p className="text-sm font-medium">{question}</p>
          <p className="text-sm text-muted-foreground">{answer}</p>
        </>
      )}
      <div className="flex flex-wrap gap-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          onClick={() => void handleAccept()}
        >
          Accept
        </Button>
        {editing ? null : (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={pending}
            onClick={() => setEditing(true)}
          >
            Edit
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          onClick={() => setResolved(true)}
        >
          Discard
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </li>
  );
}
