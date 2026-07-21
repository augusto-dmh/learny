"use client";

/**
 * Review screen (QUIZ-19, QUIZ-15) — the spaced-repetition due queue.
 *
 * Resolves auth via `/api/auth/me` (through the proxy) for the CSRF token, then
 * loads the caller's due queue (optionally filtered to one source for per-source
 * sessions). Each card shows the question only (a cloze renders its `____` blank
 * as plain text); Reveal exposes the answer plus a citation footnote (section
 * breadcrumb + source excerpt). The pin — an "Open in book" link built through
 * `readUrl`, plus the origin note when the card carries provenance — sits with the
 * question and is therefore reachable without revealing first (CAP-25..27). The
 * 4-button grade bar (Again/Hard/Good/Easy → FSRS rating 1..4) submits a
 * self-grade and auto-advances; after the last card a summary shows counts per
 * rating. Nothing due and a fetch/submit failure each settle to their own
 * readable state. The queue only ever holds active items (the server excludes
 * stale/orphaned), so no source-changed indication appears here.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth and per-user ownership on every
 * review call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { useKeyShortcuts } from "@/app/components/use-key-shortcuts";
import { readUrl } from "@/app/lib/read-url";
import {
  getDueReviews,
  resetSchedule,
  submitReview,
  type DueItem,
} from "@/app/lib/quiz";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/** The 4 FSRS self-grades, in ascending rating order (Again=1 … Easy=4). */
const GRADES: { rating: number; label: string }[] = [
  { rating: 1, label: "Again" },
  { rating: 2, label: "Hard" },
  { rating: 3, label: "Good" },
  { rating: 4, label: "Easy" },
];

/** Per-rating tally kept as the session progresses (rating → count). */
type Tally = Record<number, number>;

const EMPTY_TALLY: Tally = { 1: 0, 2: 0, 3: 0, 4: 0 };

export function ReviewScreen({
  sourceId,
  onRequireAuth,
}: {
  sourceId?: string;
  onRequireAuth?: () => void;
}) {
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [queue, setQueue] = useState<DueItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [tally, setTally] = useState<Tally>(EMPTY_TALLY);
  // When the current card's question was shown, so review duration is the
  // question-to-grade span (best-effort, optional field).
  const questionShownAt = useRef<number>(Date.now());

  const loadQueue = useCallback(async () => {
    setLoadError(null);
    setQueue(null);
    try {
      const result = await getDueReviews({ sourceId });
      setQueue(result.items);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load your due reviews.",
      );
    }
  }, [sourceId]);

  const load = useCallback(async () => {
    const next = await fetchAuthState();
    if (!next.authenticated) {
      setAuthed(false);
      onRequireAuth?.();
      return;
    }
    setCsrf(next.user.csrf_token);
    setAuthed(true);
    await loadQueue();
  }, [loadQueue, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  // Each time a new card becomes current, restart it hidden and time it afresh.
  useEffect(() => {
    setRevealed(false);
    setSubmitError(null);
    setResetError(null);
    questionShownAt.current = Date.now();
  }, [index]);

  async function handleGrade(rating: number) {
    if (!csrf || !queue || submitting) {
      return;
    }
    const item = queue[index];
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitReview(
        item.id,
        { rating, review_duration_ms: Date.now() - questionShownAt.current },
        csrf,
      );
      setTally((prev) => ({ ...prev, [rating]: prev[rating] + 1 }));
      setIndex((i) => i + 1);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not submit your review.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // The explicit, confirm-gated schedule reset (NL-12): the only non-review path
  // that changes scheduling. On success the badge retires locally and the card stays
  // on screen — a reset is a deliberate relearn, not a review, so it neither grades
  // nor advances.
  async function handleReset() {
    if (!csrf || !queue || resetting) {
      return;
    }
    const item = queue[index];
    setResetting(true);
    setResetError(null);
    try {
      await resetSchedule(item.id, csrf);
      setQueue((prev) =>
        prev
          ? prev.map((card, i) =>
              i === index ? { ...card, note_changed: false } : card,
            )
          : prev,
      );
    } catch (err) {
      setResetError(
        err instanceof Error ? err.message : "Could not reset this card's schedule.",
      );
    } finally {
      setResetting(false);
    }
  }

  // Grading on bare keys (CAP-30/31). The binding set follows the card's own
  // state so a key can only ever do the thing the card is currently offering:
  // space reveals while the answer is hidden, and 1–4 grade once it is out. The
  // shortcuts are live only while a card is actually on screen.
  const cardOnScreen = queue !== null && index < queue.length;
  useKeyShortcuts(
    revealed
      ? Object.fromEntries(
          GRADES.map((grade) => [
            String(grade.rating),
            () => void handleGrade(grade.rating),
          ]),
        )
      : { space: () => setRevealed(true) },
    cardOnScreen,
  );

  if (authed === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!authed) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  if (loadError) {
    return (
      <section aria-label="review" className="space-y-4">
        <p role="alert" className="text-sm text-destructive">
          {loadError}
        </p>
        <Button type="button" onClick={() => void loadQueue()}>
          Retry
        </Button>
      </section>
    );
  }
  if (queue === null) {
    return <p className="text-muted-foreground">Loading your due reviews…</p>;
  }
  if (queue.length === 0) {
    return (
      <section aria-label="review" className="space-y-3">
        <p className="text-muted-foreground">Nothing due right now.</p>
        <Link
          href="/sources"
          className="text-primary underline-offset-4 hover:underline"
        >
          Back to library
        </Link>
      </section>
    );
  }
  if (index >= queue.length) {
    const total = GRADES.reduce((sum, g) => sum + tally[g.rating], 0);
    return (
      <section aria-label="review summary" className="space-y-4">
        <h2 className="text-lg font-semibold">Session complete</h2>
        <p data-testid="reviewed-total" className="text-sm">
          Reviewed {total} {total === 1 ? "card" : "cards"}.
        </p>
        <ul className="space-y-1 text-sm">
          {GRADES.map((grade) => (
            <li key={grade.rating}>
              <span className="text-muted-foreground">{grade.label}:</span>{" "}
              <span data-testid={`count-${grade.label.toLowerCase()}`}>
                {tally[grade.rating]}
              </span>
            </li>
          ))}
        </ul>
        <Link
          href="/sources"
          className="text-primary underline-offset-4 hover:underline"
        >
          Back to library
        </Link>
      </section>
    );
  }

  const item = queue[index];
  return (
    <section aria-label="review" className="space-y-4">
      <p data-testid="position" className="text-sm text-muted-foreground">
        {index + 1}/{queue.length}
      </p>
      <ReviewCard
        item={item}
        revealed={revealed}
        onReveal={() => setRevealed(true)}
        onGrade={handleGrade}
        submitting={submitting}
        onReset={handleReset}
        resetting={resetting}
      />
      {resetError ? (
        <p role="alert" className="text-sm text-destructive">
          {resetError}
        </p>
      ) : null}
      {submitError ? (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-destructive">
            {submitError}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSubmitError(null)}
          >
            Try again
          </Button>
        </div>
      ) : null}
    </section>
  );
}

/** One due card: question, a Reveal toggle, then the answer + citation + grades. */
function ReviewCard({
  item,
  revealed,
  onReveal,
  onGrade,
  submitting,
  onReset,
  resetting,
}: {
  item: DueItem;
  revealed: boolean;
  onReveal: () => void;
  onGrade: (rating: number) => void;
  submitting: boolean;
  onReset: () => void;
  resetting: boolean;
}) {
  // The two-step confirm for the schedule reset lives with the card so a declined
  // confirm fires nothing (NL-12). Advancing to another card drops any open confirm
  // so it never carries forward onto the next card's badge.
  const [confirmingReset, setConfirmingReset] = useState(false);
  useEffect(() => {
    setConfirmingReset(false);
  }, [item.id]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          <Badge variant="outline">{item.item_type}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* The cloze question already carries its `____` blank — render as text. */}
        <p data-testid="question" className="text-base">
          {item.question}
        </p>

        {/*
          The pin (CAP-25/26) sits with the question rather than in the revealed
          footnote: a card the student just failed becomes a re-read only if the
          way back is reachable *before* they give up, and putting it here is what
          keeps the jump to one action (CAP-36). It carries the anchor, not the
          answer, so it leaks nothing the reveal is holding back.

          A source-less `note` card has no book to open, so the pin is absent for it;
          its provenance line links the note instead (AD-149).
        */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {item.source_id ? (
            <Link
              href={readUrl(item.source_id, item.citation.anchor)}
              className="text-primary underline-offset-4 hover:underline"
            >
              Open in book
            </Link>
          ) : null}
          {item.provenance ? (
            // A card made at a passage — or promoted from a note — additionally offers
            // the note it came from (CAP-27, NL-13). A deck card, or one whose note was
            // deleted, offers none.
            <Link
              data-testid="card-provenance"
              href={`/notes/${item.provenance.note_id}`}
              className="text-muted-foreground underline-offset-4 hover:underline"
            >
              From “{item.provenance.note_title}”
            </Link>
          ) : null}
        </div>

        {item.note_changed ? (
          // The "your note changed" badge (NL-12): the origin note was revised since
          // this card was last reviewed. It links the note (when still present) and
          // offers the explicit, confirm-gated reset — reviewing the card as-is
          // naturally retires the badge, and reset is the only way to relearn it.
          <div
            data-testid="note-changed"
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
          >
            {item.provenance ? (
              <Link
                data-testid="note-changed-badge"
                href={`/notes/${item.provenance.note_id}`}
                className="rounded-4xl bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground underline-offset-4 hover:underline"
              >
                Your note changed
              </Link>
            ) : (
              <span
                data-testid="note-changed-badge"
                className="rounded-4xl bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
              >
                Your note changed
              </span>
            )}
            {confirmingReset ? (
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">
                  Reset this card’s schedule?
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={resetting}
                  onClick={onReset}
                >
                  {resetting ? "Resetting…" : "Confirm reset"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={resetting}
                  onClick={() => setConfirmingReset(false)}
                >
                  Cancel
                </Button>
              </span>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingReset(true)}
              >
                Reset schedule
              </Button>
            )}
          </div>
        ) : null}

        {revealed ? (
          <div className="space-y-3">
            <Separator />
            <p data-testid="answer" className="text-base font-medium">
              {item.answer}
            </p>
            <figure className="space-y-1 border-l-2 pl-3 text-sm text-muted-foreground">
              <figcaption>{item.citation.section_path.join(" › ")}</figcaption>
              <blockquote>{item.citation.source_excerpt}</blockquote>
            </figure>
            <div
              role="group"
              aria-label="Grade your recall"
              className="flex flex-wrap gap-2"
            >
              {GRADES.map((grade) => (
                <Button
                  key={grade.rating}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={submitting}
                  onClick={() => onGrade(grade.rating)}
                >
                  {grade.label}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <Button type="button" onClick={onReveal}>
            Reveal answer
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
