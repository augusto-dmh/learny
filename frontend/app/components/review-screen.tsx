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
 * readable state. When the session page is exhausted and overdue cards remain,
 * Done-for-today offers Keep going (the next session page) and a continue-reading
 * link when one exists. The queue only ever holds active items (the server excludes
 * stale/orphaned), so no source-changed indication appears here. Grade buttons
 * show the server's next-interval labels. A grade whose new due is within the
 * session requeue window is inserted back into the remaining queue (not by
 * refetching the overdue pile). Space reveals while hidden and grades Good
 * once the answer is out.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth and per-user ownership on every
 * review call regardless of client-side routing (FR-AUTH-007, ADR-017).
 *
 * `onGraded` fires after each accepted grade so a host rendering this screen
 * beside its own due figure can re-read it. Whole-page hosts ignore it; the
 * reader's dock needs it, because there the count sits next to the queue being
 * drained and would otherwise keep showing the number from before the session.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { isTypingTarget, useKeyShortcuts } from "@/app/components/use-key-shortcuts";
import { readUrl } from "@/app/lib/read-url";
import {
  ensureStarterDeck,
  flagQuizItem,
  getDueReviews,
  intervalLabel,
  resetSchedule,
  submitReview,
  undoReview,
  updateQuizItem,
  type DueItem,
  type Scheduling,
} from "@/app/lib/quiz";
import { listSources } from "@/app/lib/sources";
import {
  getContinueReading,
  type ContinueReadingView,
} from "@/app/lib/study";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";

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

const DEFAULT_REQUEUE_MINUTES = 15;

/** A session card may be tagged when it was inserted as a short-term requeue. */
type SessionCard = DueItem & { shortTerm?: boolean };

function shouldRequeue(
  dueIso: string,
  requeueMinutes: number,
  nowMs: number = Date.now(),
): boolean {
  const dueMs = Date.parse(dueIso);
  if (Number.isNaN(dueMs)) {
    return false;
  }
  return Math.abs(dueMs - nowMs) <= requeueMinutes * 60 * 1000;
}

function withSubmitLabels(card: SessionCard, scheduling: Scheduling): SessionCard {
  return {
    ...card,
    due: scheduling.due,
    interval_labels: scheduling.interval_labels ?? card.interval_labels,
    shortTerm: true,
  };
}

export function ReviewScreen({
  sourceId,
  onRequireAuth,
  onGraded,
}: {
  sourceId?: string;
  onRequireAuth?: () => void;
  onGraded?: () => void;
}) {
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [queue, setQueue] = useState<SessionCard[] | null>(null);
  const [requeueMinutes, setRequeueMinutes] = useState(DEFAULT_REQUEUE_MINUTES);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [tally, setTally] = useState<Tally>(EMPTY_TALLY);
  const [remainingDue, setRemainingDue] = useState(0);
  const [draft, setDraft] = useState<{ question: string; answer: string } | null>(
    null,
  );
  const [savingEdit, setSavingEdit] = useState(false);
  // When the current card's question was shown, so review duration is the
  // question-to-grade span (best-effort, optional field).
  const questionShownAt = useRef<number>(Date.now());
  const lastGrade = useRef<{
    item: SessionCard;
    index: number;
    requeued: boolean;
  } | null>(null);

  const loadQueue = useCallback(async () => {
    setLoadError(null);
    setQueue(null);
    try {
      const result = await getDueReviews({ sourceId });
      setQueue(result.items);
      setRequeueMinutes(result.requeue_minutes ?? DEFAULT_REQUEUE_MINUTES);
      setRemainingDue(result.total_due ?? result.items.length);
      setIndex(0);
      setRevealed(false);
      setDraft(null);
      lastGrade.current = null;
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
    try {
      const sources = await listSources();
      const sample = sources.find((source) => source.is_sample);
      if (sample) {
        await ensureStarterDeck(sample.id, next.user.csrf_token);
      }
    } catch {
      // Due still loads; a missing sample or failed clone must not blank Review.
    }
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
    setDraft(null);
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
      const scheduling = await submitReview(
        item.id,
        { rating, review_duration_ms: Date.now() - questionShownAt.current },
        csrf,
      );
      const requeue = shouldRequeue(scheduling.due, requeueMinutes);
      lastGrade.current = { item, index, requeued: requeue };
      if (requeue) {
        const updated = withSubmitLabels(item, scheduling);
        setQueue((prev) =>
          prev
            ? [...prev.slice(0, index + 1), ...prev.slice(index + 1), updated]
            : prev,
        );
      } else {
        setRemainingDue((n) => Math.max(0, n - 1));
      }
      setTally((prev) => ({ ...prev, [rating]: prev[rating] + 1 }));
      setRevealed(false);
      setIndex((i) => i + 1);
      onGraded?.();
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

  async function handleUndo() {
    if (!csrf || !queue || submitting || index >= queue.length) {
      return;
    }
    setSubmitError(null);
    try {
      const scheduling = await undoReview(csrf);
      const last = lastGrade.current;
      if (last) {
        setQueue((prev) => {
          if (!prev) {
            return prev;
          }
          const next = [...prev];
          if (last.requeued) {
            const extraAt = next.findLastIndex(
              (card, i) =>
                i > last.index && card.id === last.item.id && card.shortTerm,
            );
            if (extraAt >= 0) {
              next.splice(extraAt, 1);
            }
          }
          next[last.index] = {
            ...last.item,
            due: scheduling.due,
            interval_labels:
              scheduling.interval_labels ?? last.item.interval_labels,
            shortTerm: false,
          };
          return next;
        });
        setIndex(last.index);
        if (!last.requeued) {
          setRemainingDue((n) => n + 1);
        }
        lastGrade.current = null;
      }
      setRevealed(false);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not undo your last review.",
      );
    }
  }

  async function handleFlag() {
    if (!csrf || !queue || submitting || index >= queue.length) {
      return;
    }
    const item = queue[index];
    setSubmitError(null);
    try {
      await flagQuizItem(item.id, true, csrf);
      setQueue((prev) => (prev ? prev.filter((_, i) => i !== index) : prev));
      setRemainingDue((n) => Math.max(0, n - 1));
      setRevealed(false);
      setDraft(null);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not flag this card.",
      );
    }
  }

  async function handleSaveEdit() {
    if (!csrf || !queue || !draft || savingEdit || index >= queue.length) {
      return;
    }
    const item = queue[index];
    setSavingEdit(true);
    setSubmitError(null);
    try {
      const saved = await updateQuizItem(item.id, draft, csrf);
      setQueue((prev) =>
        prev
          ? prev.map((card, i) =>
              i === index
                ? { ...card, question: saved.question, answer: saved.answer }
                : card,
            )
          : prev,
      );
      setDraft(null);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not save this card.",
      );
    } finally {
      setSavingEdit(false);
    }
  }

  function startEdit() {
    if (!queue || index >= queue.length) {
      return;
    }
    const item = queue[index];
    setDraft({ question: item.question, answer: item.answer });
  }

  // Grading on bare keys (CAP-30/31, REV-44/45). Space reveals while the answer
  // is hidden and grades Good once it is out; 1–4 grade once revealed; u/f/e
  // undo, flag, and edit. Live only while a card is on screen and not being edited.
  const cardOnScreen = queue !== null && index < queue.length && draft === null;
  useKeyShortcuts(
    revealed
      ? {
          ...Object.fromEntries(
            GRADES.map((grade) => [
              String(grade.rating),
              () => void handleGrade(grade.rating),
            ]),
          ),
          space: () => void handleGrade(3),
          u: () => void handleUndo(),
          f: () => void handleFlag(),
          e: startEdit,
        }
      : {
          space: () => setRevealed(true),
          u: () => void handleUndo(),
          f: () => void handleFlag(),
          e: startEdit,
        },
    cardOnScreen,
  );

  useEffect(() => {
    if (!cardOnScreen) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) {
        return;
      }
      if (event.key.toLowerCase() !== "z") {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      event.preventDefault();
      void handleUndo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cardOnScreen, csrf, queue, index, submitting]);

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
  if (queue.length === 0 || index >= queue.length) {
    if (remainingDue > 0) {
      return (
        <SessionDoneWithRemainder
          onKeepGoing={() => {
            setTally(EMPTY_TALLY);
            void loadQueue();
          }}
        />
      );
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
  const shortTermLeft = queue.slice(index).filter((card) => card.shortTerm).length;
  return (
    <section aria-label="review" className="space-y-4">
      <p data-testid="position" className="text-sm text-muted-foreground">
        {index + 1}/{queue.length}
      </p>
      {shortTermLeft > 0 ? (
        <p data-testid="short-term-remaining" className="text-sm text-muted-foreground">
          {shortTermLeft} still in short-term review
        </p>
      ) : null}
      <ReviewCard
        key={`${item.id}-${index}`}
        item={item}
        revealed={revealed}
        onReveal={() => setRevealed(true)}
        onGrade={handleGrade}
        submitting={submitting}
        onReset={handleReset}
        resetting={resetting}
        editor={
          draft ? (
            <ReviewCardEditor
              question={draft.question}
              answer={draft.answer}
              onQuestionChange={(question) =>
                setDraft((prev) => (prev ? { ...prev, question } : prev))
              }
              onAnswerChange={(answer) =>
                setDraft((prev) => (prev ? { ...prev, answer } : prev))
              }
              onSave={() => void handleSaveEdit()}
              onCancel={() => setDraft(null)}
              saving={savingEdit}
            />
          ) : null
        }
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

/**
 * Session page finished while overdue cards remain (REV-42): Done-for-today,
 * Keep going (next session page), and a continue-reading link when one exists.
 * Fetches continue only in this state so a caught-up summary never asks for it.
 */
function SessionDoneWithRemainder({ onKeepGoing }: { onKeepGoing: () => void }) {
  const [hero, setHero] = useState<ContinueReadingView | null | "loading">(
    "loading",
  );

  useEffect(() => {
    let active = true;
    getContinueReading()
      .then((data) => {
        if (active) {
          setHero(data);
        }
      })
      .catch(() => {
        if (active) {
          setHero(null);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section aria-label="review summary" className="space-y-4">
      <h2 data-testid="done-for-today" className="text-lg font-semibold">
        Done for today
      </h2>
      <p className="text-sm text-muted-foreground">
        You&rsquo;ve finished this session. More cards are still due when you
        want them.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" data-testid="keep-going" onClick={onKeepGoing}>
          Keep going
        </Button>
        {hero !== "loading" && hero !== null ? (
          <Link
            data-testid="continue-reading"
            href={readUrl(hero.source_id, null)}
            className="text-primary underline-offset-4 hover:underline"
          >
            Continue reading {hero.source_title}
          </Link>
        ) : null}
      </div>
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
  editor,
}: {
  item: DueItem;
  revealed: boolean;
  onReveal: () => void;
  onGrade: (rating: number) => void;
  submitting: boolean;
  onReset: () => void;
  resetting: boolean;
  editor?: ReactNode;
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
        {editor ? (
          editor
        ) : (
          <p data-testid="question" className="text-base">
            {item.question}
          </p>
        )}

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

        {editor ? null : revealed ? (
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
              {GRADES.map((grade) => {
                const interval = intervalLabel(item.interval_labels, grade.rating);
                return (
                  <Button
                    key={grade.rating}
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={submitting}
                    aria-label={grade.label}
                    onClick={() => onGrade(grade.rating)}
                  >
                    {grade.label}
                    {interval ? (
                      <span
                        data-testid={`grade-interval-${grade.rating}`}
                        className="ml-1 text-muted-foreground"
                      >
                        {interval}
                      </span>
                    ) : null}
                  </Button>
                );
              })}
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

function ReviewCardEditor({
  question,
  answer,
  onQuestionChange,
  onAnswerChange,
  onSave,
  onCancel,
  saving,
}: {
  question: string;
  answer: string;
  onQuestionChange: (value: string) => void;
  onAnswerChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <div className="space-y-1.5">
        <label htmlFor="review-edit-question" className="text-sm font-medium">
          Question
        </label>
        <Textarea
          id="review-edit-question"
          data-testid="edit-question"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="review-edit-answer" className="text-sm font-medium">
          Answer
        </label>
        <Textarea
          id="review-edit-answer"
          data-testid="edit-answer"
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={saving}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
