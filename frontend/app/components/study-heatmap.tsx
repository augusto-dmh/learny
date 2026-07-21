"use client";

/**
 * Adherence stats block (RFC-004 Cycle E — HOME-12/13/14, I-4/I-7).
 *
 * The below-the-fold half of Home: a "Studied X of the last 14 days" line and a
 * week-aligned activity heatmap, behind a device-local hide toggle. It fetches
 * the study window on its own — independent of the hero and due-card fetches — so
 * a stats failure shows a quiet inline error here without blanking the two cards
 * above (spec isolation edge).
 *
 * Two invariants shape this file:
 *  - I-4: the adherence number is the server's `studied_last_14`, rendered
 *    verbatim. This client never recomputes or stores a streak; the heatmap is a
 *    presentation of the server's per-day rows, nothing more.
 *  - I-7: zero-activity days are plain empty cells — silent grace. There is no
 *    warning, no "broken streak" messaging, no badge, popup, or celebration
 *    anywhere in this block (gamification cap).
 *
 * The backend returns only days that had activity (a sparse list), so the grid is
 * densified here: the 84-day window ending at the viewer's local today, with a row
 * looked up per day and absent days left empty.
 */

import { useEffect, useState } from "react";

import {
  getStudyDays,
  type StudyDayView,
  type StudySummaryView,
} from "@/app/lib/study";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useHomeSettings } from "./use-home-settings";

/** The heatmap window: 12 weeks, rendered as a week-aligned grid (AD-156). */
const HEATMAP_WINDOW_DAYS = 84;

/** Shading class per intensity level; level 0 is the plain empty cell (I-7). */
const LEVEL_CLASS: Record<number, string> = {
  0: "bg-muted",
  1: "bg-chart-2",
  2: "bg-chart-3",
  3: "bg-chart-4",
  4: "bg-chart-5",
};

/** A card's async state: still loading, failed, or resolved with its payload. */
type Loadable<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/** Format a local calendar date as `YYYY-MM-DD` to match the backend day keys. */
function localDayKey(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Map a day's total activity to a shading level 0..4 (0 = no activity). */
function intensityLevel(total: number): number {
  if (total <= 0) return 0;
  if (total <= 1) return 1;
  if (total <= 3) return 2;
  if (total <= 6) return 3;
  return 4;
}

type HeatmapCell = {
  key: string;
  /** The ISO day for a real cell, or `null` for a week-alignment placeholder. */
  day: string | null;
  total: number;
  level: number;
  placeholder: boolean;
};

/**
 * Densify the sparse day rows into the `HEATMAP_WINDOW_DAYS`-day window ending at
 * `today`, padded fore and aft to whole weeks so the grid renders as clean weekday
 * columns. Absent days become level-0 empty cells (silent grace).
 */
function buildCells(days: StudyDayView[], today: Date): HeatmapCell[] {
  const totals = new Map<string, number>();
  for (const row of days) {
    totals.set(row.day, row.reviews_count + row.reading_updates);
  }

  const start = new Date(today);
  start.setDate(start.getDate() - (HEATMAP_WINDOW_DAYS - 1));

  const cells: HeatmapCell[] = [];
  // Leading placeholders push the first real day into its weekday row (Sun = 0).
  for (let i = 0; i < start.getDay(); i += 1) {
    cells.push({ key: `pad-start-${i}`, day: null, total: 0, level: 0, placeholder: true });
  }
  for (let i = 0; i < HEATMAP_WINDOW_DAYS; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = localDayKey(d);
    const total = totals.get(key) ?? 0;
    cells.push({ key, day: key, total, level: intensityLevel(total), placeholder: false });
  }
  // Trailing placeholders complete the final week column.
  while (cells.length % 7 !== 0) {
    cells.push({
      key: `pad-end-${cells.length}`,
      day: null,
      total: 0,
      level: 0,
      placeholder: true,
    });
  }
  return cells;
}

/**
 * The week-aligned activity grid. Active days are shaded by their activity total;
 * zero-activity days are plain empty cells with no title or warning (I-7). `today`
 * is injectable for deterministic tests; it defaults to the current instant.
 */
export function StudyHeatmap({
  days,
  today = new Date(),
}: {
  days: StudyDayView[];
  today?: Date;
}) {
  const cells = buildCells(days, today);
  return (
    <div
      data-testid="study-heatmap"
      aria-label="study activity heatmap"
      className="grid grid-flow-col grid-rows-[repeat(7,minmax(0,1fr))] gap-1"
    >
      {cells.map((cell) =>
        cell.placeholder ? (
          <div key={cell.key} aria-hidden data-placeholder className="h-3 w-3 rounded-sm" />
        ) : (
          <div
            key={cell.key}
            data-testid="heatmap-cell"
            data-day={cell.day ?? undefined}
            data-level={cell.level}
            title={cell.total > 0 ? `${cell.total} on ${cell.day}` : undefined}
            className={`h-3 w-3 rounded-sm ${LEVEL_CLASS[cell.level]}`}
          />
        ),
      )}
    </div>
  );
}

/**
 * The adherence stats block: the streak line and heatmap behind a hide toggle,
 * fed by its own study fetch. The toggle stays put when the block is hidden so the
 * viewer can bring it back; the choice persists device-locally (HOME-14).
 */
export function StudyStats() {
  const { showStats, setShowStats } = useHomeSettings();
  const [state, setState] = useState<Loadable<StudySummaryView>>({
    status: "loading",
  });

  useEffect(() => {
    let active = true;
    getStudyDays(HEATMAP_WINDOW_DAYS)
      .then((data) => {
        if (active) setState({ status: "ready", data });
      })
      .catch((err: unknown) => {
        if (active)
          setState({
            status: "error",
            message:
              err instanceof Error
                ? err.message
                : "Could not load your study activity.",
          });
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card aria-label="study stats">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Study activity</CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowStats(!showStats)}
        >
          {showStats ? "Hide stats" : "Show stats"}
        </Button>
      </CardHeader>
      {showStats && (
        <CardContent className="space-y-4">
          {state.status === "loading" ? (
            <Skeleton className="h-24 w-full" />
          ) : state.status === "error" ? (
            <p role="alert" className="text-sm text-destructive">
              {state.message}
            </p>
          ) : (
            <>
              <p data-testid="streak-line" className="text-sm text-muted-foreground">
                Studied {state.data.studied_last_14} of the last 14 days
              </p>
              <StudyHeatmap days={state.data.days} />
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
