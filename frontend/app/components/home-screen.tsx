"use client";

/**
 * Home screen (RFC-004 Cycle E — HOME-02/03/05/06).
 *
 * The "what should I do right now" surface: a continue-reading hero and a
 * due-reviews card, each fed by its own fetch. The two loads are deliberately
 * independent — one failing shows that card's quiet error while the other still
 * renders (spec edge case) — so there is no shared gate that could blank both.
 * Auth is not resolved here: the `(app)` shell header owns the 401 → /login
 * redirect (FR-AUTH-007, ADR-017), so an unauthenticated visitor is bounced by
 * the shell rather than by this screen.
 *
 * The hero resume link points at `/sources/{id}/read` with no anchor and relies
 * on the reader's existing resume path to restore the stored position (HOME-03) —
 * no new reader behavior. The done-for-today state is calm by design: no XP,
 * badge, popup, streak pressure, or celebratory animation (RFC-004 gamification
 * cap, I-7).
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { InkLine } from "@/app/components/ink-line";
import { getContinueReading, type ContinueReadingView } from "@/app/lib/study";
import { getDueReviews } from "@/app/lib/quiz";
import { readUrl } from "@/app/lib/read-url";
import { StudyStats } from "./study-heatmap";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** A card's async state: still loading, failed, or resolved with its payload. */
type Loadable<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

export function HomeScreen() {
  const [hero, setHero] = useState<Loadable<ContinueReadingView | null>>({
    status: "loading",
  });
  const [due, setDue] = useState<Loadable<number>>({ status: "loading" });

  useEffect(() => {
    let active = true;
    getContinueReading()
      .then((data) => {
        if (active) setHero({ status: "ready", data });
      })
      .catch((err: unknown) => {
        if (active)
          setHero({
            status: "error",
            message:
              err instanceof Error
                ? err.message
                : "Could not load your reading progress.",
          });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    // Only the count is read (AD-156: no dedicated count endpoint), so the queue
    // is capped at one item to keep the payload small.
    getDueReviews({ limit: 1 })
      .then((queue) => {
        if (active) setDue({ status: "ready", data: queue.total_due });
      })
      .catch((err: unknown) => {
        if (active)
          setDue({
            status: "error",
            message:
              err instanceof Error
                ? err.message
                : "Could not load your due reviews.",
          });
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <section
        aria-label="home"
        className="grid gap-4 md:grid-cols-2"
      >
        <ContinueHero state={hero} />
        <DueCard state={due} />
      </section>
      <StudyStats />
    </div>
  );
}

/** The continue-reading hero: resume the current book, or pick one to start. */
function ContinueHero({ state }: { state: Loadable<ContinueReadingView | null> }) {
  return (
    <Card aria-label="continue reading">
      <CardHeader>
        <CardTitle>Continue reading</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {state.status === "loading" ? (
          <Skeleton className="h-16 w-full" />
        ) : state.status === "error" ? (
          <p role="alert" className="text-sm text-destructive">
            {state.message}
          </p>
        ) : state.data === null ? (
          // New-user / empty hero: nothing to resume, so point at the bookshelf.
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              You have no book in progress yet.
            </p>
            <Button asChild>
              <Link href="/sources">Pick a book</Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1">
              <p data-testid="hero-title" className="font-medium">
                {state.data.source_title}
              </p>
              <p data-testid="hero-chapter" className="text-sm text-muted-foreground">
                {state.data.chapter_title}
              </p>
              <p data-testid="hero-percent" className="text-sm text-muted-foreground">
                {Math.round(state.data.percent)}% read
              </p>
            </div>
            <InkLine percent={state.data.percent} />
            <Button asChild>
              <Link href={readUrl(state.data.source_id, null)}>Resume</Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** The due-reviews card: start a session, or a calm done-for-today state. */
function DueCard({ state }: { state: Loadable<number> }) {
  return (
    <Card aria-label="due reviews">
      <CardHeader>
        <CardTitle>Reviews</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {state.status === "loading" ? (
          <Skeleton className="h-16 w-full" />
        ) : state.status === "error" ? (
          <p role="alert" className="text-sm text-destructive">
            {state.message}
          </p>
        ) : state.data > 0 ? (
          <div className="space-y-3">
            <p data-testid="due-count" className="text-sm">
              You have {state.data} {state.data === 1 ? "card" : "cards"} due.
            </p>
            <Button asChild>
              <Link href="/review">Review</Link>
            </Button>
          </div>
        ) : (
          // Calm done-for-today: no count, CTA, badge, or celebration (I-7).
          <p data-testid="due-done" className="text-sm text-muted-foreground">
            You&rsquo;re all caught up for today.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
