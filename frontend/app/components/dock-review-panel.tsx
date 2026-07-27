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
 */

import { useCallback, useEffect, useState } from "react";

import { getDueReviews } from "@/app/lib/quiz";

import { ReviewScreen } from "./review-screen";

/** How many of this book's cards are due, or why the figure is missing. */
export type BookDue = {
  total: number | null;
  error: string | null;
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
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const queue = await getDueReviews({ sourceId, limit: 1 });
      setTotal(queue.total_due ?? 0);
      setError(null);
    } catch (err) {
      setTotal(null);
      setError(
        err instanceof Error
          ? err.message
          : "Could not load what is due from this book.",
      );
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return { total, error };
}

export function DockReviewPanel({
  sourceId,
  total,
  error,
  onRequireAuth,
}: BookDue & { sourceId: string; onRequireAuth?: () => void }) {
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (total === null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (total === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing due from this book right now.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p data-testid="due-count" className="text-2xl font-semibold">
          {total}
        </p>
        <p className="text-sm text-muted-foreground">
          cards due from this book
        </p>
      </div>
      <ReviewScreen sourceId={sourceId} onRequireAuth={onRequireAuth} />
    </div>
  );
}
