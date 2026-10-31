"use client";

/**
 * The dock's Review tab — what this book has waiting, and the grading for it.
 *
 * The grading UI is the shipped review screen, scoped to the book and rendered
 * here rather than linked to: reviewing a book you are reading should not mean
 * leaving it, and the queue, the reveal, the grade bar, and the session summary
 * already exist. Nothing is built a second time in a narrower column.
 *
 * The figure above it is a queue inventory and nothing else — how many cards are
 * waiting, with no streak, no badge, and nothing about being behind. A book with
 * nothing due says so and offers no grading; there is nothing to grade.
 *
 * Beneath the inventory sits this book's calibration: how often feeling sure
 * meant recalling, per confidence level. It is a mirror, not a score — no
 * overall percentage, and a book with no confident grades yet says so instead
 * of showing empty rows.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { getCalibration, getDueReviews } from "@/app/lib/quiz";
import type { CalibrationLevel } from "@/app/lib/quiz";

import { ReviewScreen } from "./review-screen";
import { useErrorMessage } from "./use-error-message";

/** How many of this book's cards are due, or why the figure is missing. */
export type BookDue = {
  total: number | null;
  error: string | null;
  /** Re-read the count — the queue is drained inside the dock, beside this figure. */
  refresh: () => void;
};

/**
 * This book's due count. It asks for a single card because the total the server
 * returns is the full count before the limit — the tab needs the number, not the
 * queue, and the review screen loads the queue for itself when it is rendered.
 *
 * It lives in the dock shell rather than the panel because the tab's count has to
 * be there whether or not the reader is looking at the tab.
 */
export function useDueCount(sourceId: string): BookDue {
  const errorMessage = useErrorMessage();
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const queue = await getDueReviews({ sourceId, limit: 1 });
      setTotal(queue.total_due ?? 0);
      setError(null);
    } catch (err) {
      setTotal(null);
      setError(errorMessage(err, "quizDue"));
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return { total, error, refresh: () => void load() };
}

/** This book's calibration rows, or why they are missing. `refresh` re-reads
 * them — the mirror sits beside the grading that feeds it, so a grade re-reads
 * it in place. */
function useCalibration(
  sourceId: string,
): { levels: CalibrationLevel[] | null; error: string | null; refresh: () => void } {
  const errorMessage = useErrorMessage();
  const [levels, setLevels] = useState<CalibrationLevel[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLevels(await getCalibration(sourceId));
      setError(null);
    } catch (err) {
      setLevels(null);
      setError(errorMessage(err, "quizCalibration"));
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return { levels, error, refresh: () => void load() };
}

/** The calibration block: a level line per confidence level that has attempts. */
function Calibration({ levels, error }: { levels: CalibrationLevel[] | null; error: string | null }) {
  const t = useTranslations("chat.dockReview");
  const tConfidence = useTranslations("checkpoint.confidence");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  if (error !== null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (levels === null) {
    return <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>;
  }
  const withAttempts = levels.filter((level) => level.attempts > 0);
  if (withAttempts.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="calibration-empty">
        {t("calibrationEmpty")}
      </p>
    );
  }
  const number = (value: number) => new Intl.NumberFormat(locale).format(value);
  return (
    <ul className="space-y-1" data-testid="calibration-lines">
      {withAttempts.map((level) => (
        <li key={level.confidence} className="text-sm text-muted-foreground">
          {t("calibrationLine", {
            level: tConfidence(
              level.confidence === 1 ? "notSure" : level.confidence === 2 ? "fairlySure" : "sure",
            ),
            recalled: number(level.recalled),
            attempts: number(level.attempts),
          })}
        </li>
      ))}
    </ul>
  );
}

export function DockReviewPanel({
  sourceId,
  total,
  error,
  refresh,
  onRequireAuth,
}: BookDue & { sourceId: string; onRequireAuth?: () => void }) {
  const t = useTranslations("chat.dockReview");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const calibration = useCalibration(sourceId);
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (total === null) {
    return <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>;
  }

  return (
    <div className="space-y-4">
      {total === 0 ? (
        <p className="text-sm text-muted-foreground">{t("nothingDue")}</p>
      ) : (
        <div>
          <p data-testid="due-count" className="text-2xl font-semibold">
            {new Intl.NumberFormat(locale).format(total)}
          </p>
          <p className="text-sm text-muted-foreground">
            {t("dueCaption", { count: total })}
          </p>
        </div>
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium">{t("calibrationHeading")}</p>
        <Calibration levels={calibration.levels} error={calibration.error} />
      </div>
      {total > 0 ? (
        <ReviewScreen
          sourceId={sourceId}
          onRequireAuth={onRequireAuth}
          onGraded={() => {
            refresh();
            calibration.refresh();
          }}
        />
      ) : null}
    </div>
  );
}
