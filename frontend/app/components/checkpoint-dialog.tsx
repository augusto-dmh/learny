"use client";

/**
 * The end-of-section checkpoint: predict, recall the section's cards unaided,
 * explain the section from memory, then self-assess. FSRS schedules every attempt.
 *
 * A dialog rather than an inline panel. While the learner retrieves, the passage
 * they just read is covered, so the answer is not one scroll away. Closing it at
 * any step returns them to the same place in the book. Grades already submitted
 * are saved, because each one is its own request, so the checkpoint never holds
 * reading hostage.
 *
 * What the learner sees is ordered by the server's guarantees:
 *
 * - Nothing is requested until a prediction is chosen (or skipped).
 * - A recall's answer appears only when the call that stores the attempt
 *   resolves. The confidence buttons are the only way to submit, so every
 *   attempt carries a confidence taken before the answer was seen.
 * - On the explanation, the confidence buttons are the primary path.
 *   "Just explain" is a quiet secondary action, never the default. Using it
 *   marks the attempt assisted server-side.
 * - Feedback quotes the passage and never grades. The self-assessment that
 *   follows is the learner's own.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  CheckpointError,
  gradeAttempt,
  respondToAttempt,
  revealPassage,
  startCheckpoint,
  type Checkpoint,
  type CitationQuote,
  type Confidence,
  type ExplainFeedback,
  type Prediction,
  type RecallReveal,
} from "@/app/lib/checkpoints";

const PREDICTIONS: { value: Exclude<Prediction, null>; label: string }[] = [
  { value: 1, label: "Little" },
  { value: 2, label: "Some" },
  { value: 3, label: "Most" },
];

export const CONFIDENCES: { value: Confidence; label: string }[] = [
  { value: 1, label: "Not sure" },
  { value: 2, label: "Fairly sure" },
  { value: 3, label: "Sure" },
];

const RECALL_GRADES = [
  { rating: 1, label: "Again" },
  { rating: 2, label: "Hard" },
  { rating: 3, label: "Good" },
  { rating: 4, label: "Easy" },
];

const EXPLAIN_GRADES = [
  { rating: 1, label: "Missed it" },
  { rating: 2, label: "Partly" },
  { rating: 3, label: "Got it" },
];

type Phase =
  | { step: "predict" }
  | { step: "ask"; index: number; passage: CitationQuote | null }
  | { step: "recalled"; index: number; reveal: RecallReveal }
  | { step: "feedback"; index: number; feedback: ExplainFeedback }
  | { step: "done" };

export function CheckpointDialog({
  open,
  sourceId,
  anchor,
  sectionTitle,
  csrf,
  onClose,
  onRequireAuth,
}: {
  open: boolean;
  sourceId: string;
  anchor: string;
  sectionTitle: string;
  csrf: string;
  onClose: () => void;
  /** Called when a request finds the session gone (401), as the reader does. */
  onRequireAuth?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>({ step: "predict" });
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      if (err instanceof CheckpointError && err.status === 401 && onRequireAuth) {
        onRequireAuth();
        return;
      }
      setError(err instanceof CheckpointError ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  function advance(index: number) {
    setDraft("");
    const next = index + 1;
    if (checkpoint && next < checkpoint.attempts.length) {
      setPhase({ step: "ask", index: next, passage: null });
    } else {
      setPhase({ step: "done" });
    }
  }

  function handlePredict(prediction: Prediction) {
    void run(async () => {
      const started = await startCheckpoint(sourceId, anchor, prediction, csrf);
      setCheckpoint(started);
      setPhase({ step: "ask", index: 0, passage: null });
    });
  }

  function handleRespond(index: number, confidence: Confidence) {
    const attempt = checkpoint!.attempts[index];
    void run(async () => {
      if (attempt.kind === "recall") {
        const reveal = await respondToAttempt<RecallReveal>(
          attempt.attempt_id,
          draft,
          confidence,
          csrf,
        );
        setPhase({ step: "recalled", index, reveal });
      } else {
        const feedback = await respondToAttempt<ExplainFeedback>(
          attempt.attempt_id,
          draft,
          confidence,
          csrf,
        );
        setPhase({ step: "feedback", index, feedback });
      }
    });
  }

  function handleJustExplain(index: number) {
    const attempt = checkpoint!.attempts[index];
    void run(async () => {
      const revealed = await revealPassage(attempt.attempt_id, csrf);
      setPhase({
        step: "ask",
        index,
        passage: {
          anchor: revealed.anchor,
          section_path: revealed.section_path,
          quote: revealed.passage,
        },
      });
    });
  }

  function handleGrade(index: number, rating: number) {
    const attempt = checkpoint!.attempts[index];
    void run(async () => {
      await gradeAttempt(attempt.attempt_id, rating, csrf);
      advance(index);
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <DialogContent data-testid="checkpoint-dialog" className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Check yourself</DialogTitle>
          <DialogDescription>{sectionTitle}</DialogDescription>
        </DialogHeader>
        {phase.step === "predict" ? (
          <section className="space-y-3">
            <p className="text-sm">
              Before you start: how much of this section could you explain right now,
              without looking?
            </p>
            <div className="flex flex-wrap gap-2">
              {PREDICTIONS.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handlePredict(option.value)}
                >
                  {option.label}
                </Button>
              ))}
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => handlePredict(null)}
              >
                Skip
              </Button>
            </div>
          </section>
        ) : null}
        {phase.step === "ask" && checkpoint ? (
          <AskStep
            kind={checkpoint.attempts[phase.index].kind}
            question={checkpoint.attempts[phase.index].question}
            position={phase.index + 1}
            total={checkpoint.attempts.length}
            draft={draft}
            onDraftChange={setDraft}
            passage={phase.passage}
            pending={pending}
            onRespond={(confidence) => handleRespond(phase.index, confidence)}
            onJustExplain={() => handleJustExplain(phase.index)}
          />
        ) : null}
        {phase.step === "recalled" ? (
          <section className="space-y-3" data-testid="checkpoint-recalled">
            <Quote label="Answer" text={phase.reveal.answer} />
            <Quote
              label={phase.reveal.section_path.join(" › ")}
              text={phase.reveal.source_excerpt}
            />
            <p className="text-sm">How did that go?</p>
            <div className="flex flex-wrap gap-2">
              {RECALL_GRADES.map((grade) => (
                <Button
                  key={grade.rating}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handleGrade(phase.index, grade.rating)}
                >
                  {grade.label}
                </Button>
              ))}
            </div>
          </section>
        ) : null}
        {phase.step === "feedback" ? (
          <section className="space-y-3" data-testid="checkpoint-feedback">
            <p className="text-sm whitespace-pre-line">{phase.feedback.feedback}</p>
            {phase.feedback.citations.map((citation, index) => (
              <Quote
                key={index}
                label={citation.section_path.join(" › ")}
                text={citation.quote}
              />
            ))}
            <p className="text-sm">Compared with the passage, your explanation…</p>
            <div className="flex flex-wrap gap-2">
              {EXPLAIN_GRADES.map((grade) => (
                <Button
                  key={grade.rating}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handleGrade(phase.index, grade.rating)}
                >
                  {grade.label}
                </Button>
              ))}
            </div>
          </section>
        ) : null}
        {phase.step === "done" ? (
          <section className="space-y-3">
            <p className="text-sm">
              Saved. What you missed comes back soon in Review, and the rest returns when
              it is due.
            </p>
            <Button type="button" onClick={onClose}>
              Back to the book
            </Button>
          </section>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function AskStep({
  kind,
  question,
  position,
  total,
  draft,
  onDraftChange,
  passage,
  pending,
  onRespond,
  onJustExplain,
}: {
  kind: "recall" | "explain";
  question: string;
  position: number;
  total: number;
  draft: string;
  onDraftChange: (value: string) => void;
  passage: CitationQuote | null;
  pending: boolean;
  onRespond: (confidence: Confidence) => void;
  onJustExplain: () => void;
}) {
  const explain = kind === "explain";
  return (
    <section className="space-y-3" data-testid={`checkpoint-ask-${kind}`}>
      <p className="text-xs text-muted-foreground">
        {position} of {total}
      </p>
      <p className="font-medium">{question}</p>
      {passage ? <Quote label={passage.section_path.join(" › ")} text={passage.quote} /> : null}
      <Textarea
        aria-label={explain ? "Your explanation" : "Your answer"}
        placeholder={
          explain
            ? "Explain it as if to a friend who has not read it."
            : "Write what you remember, or leave it blank."
        }
        value={draft}
        maxLength={4000}
        onChange={(event) => onDraftChange(event.target.value)}
      />
      <p className="text-sm">How sure are you?</p>
      <div className="flex flex-wrap gap-2">
        {CONFIDENCES.map((option) => (
          <Button
            key={option.value}
            type="button"
            disabled={pending}
            onClick={() => onRespond(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>
      {explain && !passage ? (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="px-0"
          disabled={pending}
          onClick={onJustExplain}
        >
          Just explain
        </Button>
      ) : null}
    </section>
  );
}

function Quote({ label, text }: { label: string; text: string }) {
  return (
    <figure className="rounded-md border bg-muted/40 p-3">
      {label ? <figcaption className="mb-1 text-xs text-muted-foreground">{label}</figcaption> : null}
      <blockquote className="text-sm whitespace-pre-line">{text}</blockquote>
    </figure>
  );
}
