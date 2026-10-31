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

import { useTranslations } from "next-intl";
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
import { useErrorMessage } from "@/app/components/use-error-message";
import {
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
import { ApiError } from "@/app/lib/errors";

const PREDICTIONS = [
  { value: 1, key: "little" },
  { value: 2, key: "some" },
  { value: 3, key: "most" },
] as const satisfies readonly { value: Exclude<Prediction, null>; key: string }[];

export const CONFIDENCES = [
  { value: 1, key: "notSure" },
  { value: 2, key: "fairlySure" },
  { value: 3, key: "sure" },
] as const satisfies readonly { value: Confidence; key: string }[];

const RECALL_GRADES = [
  { rating: 1, key: "again" },
  { rating: 2, key: "hard" },
  { rating: 3, key: "good" },
  { rating: 4, key: "easy" },
] as const;

const EXPLAIN_GRADES = [
  { rating: 1, key: "missed" },
  { rating: 2, key: "partly" },
  { rating: 3, key: "gotIt" },
] as const;

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
  const t = useTranslations("checkpoint");
  const errorMessage = useErrorMessage();
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
      if (err instanceof ApiError && err.status === 401 && onRequireAuth) {
        onRequireAuth();
        return;
      }
      setError(errorMessage(err, "generic"));
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
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{sectionTitle}</DialogDescription>
        </DialogHeader>
        {phase.step === "predict" ? (
          <section className="space-y-3">
            <p className="text-sm">{t("predict.prompt")}</p>
            <div className="flex flex-wrap gap-2">
              {PREDICTIONS.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handlePredict(option.value)}
                >
                  {t(`predict.${option.key}`)}
                </Button>
              ))}
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => handlePredict(null)}
              >
                {t("predict.skip")}
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
            <Quote label={t("recalled.answer")} text={phase.reveal.answer} />
            <Quote
              label={phase.reveal.section_path.join(" › ")}
              text={phase.reveal.source_excerpt}
            />
            <p className="text-sm">{t("recalled.howDidItGo")}</p>
            <div className="flex flex-wrap gap-2">
              {RECALL_GRADES.map((grade) => (
                <Button
                  key={grade.rating}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handleGrade(phase.index, grade.rating)}
                >
                  {t(`recalled.${grade.key}`)}
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
            <p className="text-sm">{t("feedback.compared")}</p>
            <div className="flex flex-wrap gap-2">
              {EXPLAIN_GRADES.map((grade) => (
                <Button
                  key={grade.rating}
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => handleGrade(phase.index, grade.rating)}
                >
                  {t(`feedback.${grade.key}`)}
                </Button>
              ))}
            </div>
          </section>
        ) : null}
        {phase.step === "done" ? (
          <section className="space-y-3">
            <p className="text-sm">{t("done.saved")}</p>
            <Button type="button" onClick={onClose}>
              {t("done.back")}
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
  const t = useTranslations("checkpoint");
  const explain = kind === "explain";
  return (
    <section className="space-y-3" data-testid={`checkpoint-ask-${kind}`}>
      <p className="text-xs text-muted-foreground">
        {t("ask.position", { position, total })}
      </p>
      <p className="font-medium">{question}</p>
      {passage ? <Quote label={passage.section_path.join(" › ")} text={passage.quote} /> : null}
      <Textarea
        aria-label={explain ? t("ask.explanationLabel") : t("ask.answerLabel")}
        placeholder={explain ? t("ask.explanationPlaceholder") : t("ask.answerPlaceholder")}
        value={draft}
        maxLength={4000}
        onChange={(event) => onDraftChange(event.target.value)}
      />
      <p className="text-sm">{t("ask.howSure")}</p>
      <div className="flex flex-wrap gap-2">
        {CONFIDENCES.map((option) => (
          <Button
            key={option.value}
            type="button"
            disabled={pending}
            onClick={() => onRespond(option.value)}
          >
            {t(`confidence.${option.key}`)}
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
          {t("ask.justExplain")}
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
