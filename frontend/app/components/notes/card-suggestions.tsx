"use client";

/**
 * Card suggestion chips (CAP-01, CAP-05..08) — the row the reader raises after a
 * highlighted passage has produced candidates.
 *
 * Each candidate is one chip the student resolves individually: Accept persists it
 * as a scheduled card, Edit opens the question and answer inline so the *edited*
 * text is what gets persisted, and Discard drops it client-side without touching
 * the network. Nothing here is persisted until an Accept — the candidates live in
 * this component's state and vanish with it (AD-134), which is what makes "never
 * silently, never in bulk" a structural property rather than a policy.
 *
 * Pending and error state are per chip, so one failed Accept never blocks the other
 * candidates and the failed chip stays on screen to be retried. An empty candidate
 * list is a normal outcome — "no cards for this passage" — not an error, because the
 * generator dropping every candidate through groundedness QC is a quality result,
 * not a failure.
 */

import { useEffect, useState } from "react";

import { acceptCard, type Card, type CardSuggestion } from "@/app/lib/cards";
import { Button } from "@/components/ui/button";

/**
 * The chip row for one highlight's candidates. `suggestions` is the batch the
 * reader just generated; `onAccepted` reports each persisted card up, and
 * `onDismiss` fires once every chip has been resolved so the reader can tear the
 * row down.
 */
export function CardSuggestions({
  sourceId,
  noteAnchorId,
  csrf,
  suggestions,
  onAccepted,
  onDismiss,
}: {
  sourceId: string;
  noteAnchorId: string;
  csrf: string;
  suggestions: CardSuggestion[];
  onAccepted?: (card: Card) => void;
  onDismiss?: () => void;
}) {
  // Which chips the student has already resolved (accepted or discarded). Indexes
  // into `suggestions`, reset whenever a fresh batch arrives.
  const [resolved, setResolved] = useState<number[]>([]);
  useEffect(() => {
    setResolved([]);
  }, [suggestions]);

  const remaining = suggestions.filter((_, index) => !resolved.includes(index));

  function resolve(index: number) {
    const next = resolved.includes(index) ? resolved : [...resolved, index];
    setResolved(next);
    if (next.length === suggestions.length) {
      onDismiss?.();
    }
  }

  return (
    <section
      aria-label="Card suggestions"
      className="mt-2 flex flex-col gap-2 rounded-md border bg-card p-2"
    >
      {suggestions.length === 0 ? (
        // A generation that yielded nothing usable is reported as an outcome, not
        // an error: there is simply nothing here worth remembering.
        <p className="text-xs text-muted-foreground">No cards for this passage.</p>
      ) : remaining.length === 0 ? (
        <p className="text-xs text-muted-foreground">All suggestions handled.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {suggestions.map((suggestion, index) =>
            resolved.includes(index) ? null : (
              <SuggestionChip
                key={`${suggestion.question}-${index}`}
                sourceId={sourceId}
                noteAnchorId={noteAnchorId}
                csrf={csrf}
                suggestion={suggestion}
                onAccepted={(card) => {
                  onAccepted?.(card);
                  resolve(index);
                }}
                onDiscard={() => resolve(index)}
              />
            ),
          )}
        </ul>
      )}
    </section>
  );
}

/**
 * One candidate. Holds its own draft text, pending flag, and error so the three
 * verbs are independent per chip.
 *
 * Accept posts the draft — which is the generated text until the student edits it,
 * and their own words afterwards. Discard is deliberately local: it calls nothing,
 * because a candidate that was never persisted has nothing to delete.
 */
function SuggestionChip({
  sourceId,
  noteAnchorId,
  csrf,
  suggestion,
  onAccepted,
  onDiscard,
}: {
  sourceId: string;
  noteAnchorId: string;
  csrf: string;
  suggestion: CardSuggestion;
  onAccepted: (card: Card) => void;
  onDiscard: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(suggestion.question);
  const [answer, setAnswer] = useState(suggestion.answer);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAccept() {
    let accepted = false;
    setPending(true);
    setError(null);
    try {
      // Both 201 (newly created) and 200 (an idempotent re-accept of the same text
      // from the same highlight) resolve here — a double submit yields one card,
      // and the second answer is a success, not something to retry.
      const card = await acceptCard(
        sourceId,
        {
          note_anchor_id: noteAnchorId,
          item_type: suggestion.item_type,
          question,
          answer,
        },
        csrf,
      );
      accepted = true;
      onAccepted(card);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save this card.",
      );
    } finally {
      // The chip unmounts on success; only a failure needs its pending flag back.
      if (!accepted) {
        setPending(false);
      }
    }
  }

  return (
    <li
      data-testid="card-suggestion"
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
          onClick={handleAccept}
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
          onClick={onDiscard}
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
