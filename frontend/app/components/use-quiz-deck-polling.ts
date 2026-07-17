"use client";

/**
 * Quiz-deck generation polling (QUIZ-20).
 *
 * While a source's deck job is in flight (`active`), poll its quiz overview
 * every 3s and hand each result back to the caller so it can refresh counts and
 * detect the terminal transition. The caller flips `active` to false once the
 * overview's job reaches a terminal state, which clears the timer; the timer is
 * also cleared on unmount. A failed poll tick is skipped silently — the overview
 * is left unchanged and polling continues on the next interval. Mirrors
 * `use-ingestion-polling` (AD-070).
 */

import { useEffect } from "react";

import { getQuizOverview, type QuizOverview } from "@/app/lib/quiz";

const POLL_INTERVAL_MS = 3000;

export function useQuizDeckPolling(
  sourceId: string,
  active: boolean,
  onOverview: (overview: QuizOverview) => void,
): void {
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = setInterval(() => {
      getQuizOverview(sourceId)
        .then(onOverview)
        .catch(() => {
          // Transient read failure — skip this tick, keep polling.
        });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [sourceId, active, onOverview]);
}
