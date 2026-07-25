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
 *
 * The grid is laid out on fixed tracks. Declaring seven rows without a column
 * track left the implicit columns at `auto`, so they stretched to whatever width
 * the card offered and the cells read as scattered squares; the column track, the
 * cell size, and the start alignment are what make it a compact block. The two
 * axes and the legend hang off the same tracks, so they stay in step with the
 * cells at any width.
 */

import { useCallback, useEffect, useState, type CSSProperties } from "react";

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

/** The window in weeks — one grid column per week, and the graph's own label. */
const HEATMAP_WINDOW_WEEKS = HEATMAP_WINDOW_DAYS / 7;

/** Cell edge and gutter, in px: the fixed tracks the grid is laid out on. */
const CELL_PX = 15;
const GAP_PX = 4;

/** Shading class per intensity level; level 0 is the plain empty cell (I-7). */
const LEVEL_CLASS: Record<number, string> = {
  0: "bg-muted",
  1: "bg-chart-2",
  2: "bg-chart-3",
  3: "bg-chart-4",
  4: "bg-chart-5",
};

/** The five levels, low to high — the order the Less→More key names them in. */
const LEVELS = [0, 1, 2, 3, 4];

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * The weekday rows that carry a label. Naming every other row keeps the axis
 * readable without crowding it; the unlabelled rows still render a spacer so the
 * axis stays in step with the cell grid.
 */
const WEEKDAY_LABEL_ROWS = [1, 3, 5];

/**
 * The cell grid: fixed rows *and* a fixed implicit column track, start-aligned so
 * the block keeps its natural width instead of stretching across the card.
 */
const CELLS_GRID_STYLE: CSSProperties = {
  display: "grid",
  gridAutoFlow: "column",
  gridTemplateRows: `repeat(7, ${CELL_PX}px)`,
  gridAutoColumns: `${CELL_PX}px`,
  gap: `${GAP_PX}px`,
  justifyContent: "start",
};

/** The month axis: the same column track as the cells, so labels sit over them. */
const MONTHS_AXIS_STYLE: CSSProperties = {
  display: "grid",
  gridAutoFlow: "column",
  gridAutoColumns: `${CELL_PX}px`,
  gap: `${GAP_PX}px`,
  justifyContent: "start",
  height: "14px",
};

/** The weekday axis: the same row track as the cells, so labels sit beside them. */
const WEEKDAYS_AXIS_STYLE: CSSProperties = {
  display: "grid",
  gridTemplateRows: `repeat(7, ${CELL_PX}px)`,
  gap: `${GAP_PX}px`,
  paddingRight: "4px",
};

const CELL_SIZE_STYLE: CSSProperties = {
  width: `${CELL_PX}px`,
  height: `${CELL_PX}px`,
};

/** The hairline that gives an unshaded cell definition without giving it colour. */
const CELL_BASE_CLASS = "rounded-[3px] inset-ring-1 inset-ring-foreground/5";

/** The quiet mono voice both axes and the legend speak in. */
const AXIS_TEXT_CLASS =
  "font-mono text-[10.5px] tracking-[0.04em] text-muted-foreground";

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
  /** The day as a reader says it: `Tue, Jul 21`. */
  label: string;
  /** Zero-based month, for placing each month label over its own column. */
  month: number;
  reviews: number;
  /** The day's reading volume as the server floored it — never derived here. */
  pages: number;
  total: number;
  level: number;
  /** Whether this cell is the viewer's local today, which the grid rings. */
  today: boolean;
  placeholder: boolean;
};

/** The fields a placeholder has nothing to say about. */
const BLANK_CELL = { label: "", month: 0, reviews: 0, pages: 0 };

/**
 * Densify the sparse day rows into the `HEATMAP_WINDOW_DAYS`-day window ending at
 * `today`, padded fore and aft to whole weeks so the grid renders as clean weekday
 * columns. Absent days become level-0 empty cells (silent grace).
 *
 * Shading stays a function of `reviews_count + reading_updates` alone; the pages
 * figure rides along for the tooltip and moves no cell's level.
 */
function buildCells(days: StudyDayView[], today: Date): HeatmapCell[] {
  const rows = new Map<string, StudyDayView>();
  for (const row of days) {
    rows.set(row.day, row);
  }

  const todayKey = localDayKey(today);
  const start = new Date(today);
  start.setDate(start.getDate() - (HEATMAP_WINDOW_DAYS - 1));

  const cells: HeatmapCell[] = [];
  // Leading placeholders push the first real day into its weekday row (Sun = 0).
  for (let i = 0; i < start.getDay(); i += 1) {
    cells.push({
      key: `pad-start-${i}`,
      day: null,
      ...BLANK_CELL,
      total: 0,
      level: 0,
      today: false,
      placeholder: true,
    });
  }
  for (let i = 0; i < HEATMAP_WINDOW_DAYS; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = localDayKey(d);
    const row = rows.get(key);
    const total = row ? row.reviews_count + row.reading_updates : 0;
    cells.push({
      key,
      day: key,
      label: `${WEEKDAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`,
      month: d.getMonth(),
      reviews: row?.reviews_count ?? 0,
      pages: row?.pages ?? 0,
      total,
      level: intensityLevel(total),
      today: key === todayKey,
      placeholder: false,
    });
  }
  // Trailing placeholders complete the final week column.
  while (cells.length % 7 !== 0) {
    cells.push({
      key: `pad-end-${cells.length}`,
      day: null,
      ...BLANK_CELL,
      total: 0,
      level: 0,
      today: false,
      placeholder: true,
    });
  }
  return cells;
}

type MonthLabel = { key: string; column: number; label: string };

/**
 * Place a month label over the column where that month's first day lands. The
 * final column is skipped: a label there would name a month the grid has barely
 * started, with no column left to carry it.
 */
function monthLabels(cells: HeatmapCell[]): MonthLabel[] {
  const columns = cells.length / 7;
  const labels: MonthLabel[] = [];
  let labelled = -1;
  for (let column = 0; column < columns; column += 1) {
    const first = cells
      .slice(column * 7, column * 7 + 7)
      .find((cell) => !cell.placeholder);
    if (!first || first.month === labelled) continue;
    labelled = first.month;
    if (column < columns - 1) {
      labels.push({
        key: `${first.month}-${column}`,
        column: column + 1,
        label: MONTHS[first.month],
      });
    }
  }
  return labels;
}

/** `2 reviews`, `1 review` — a count with its word, pluralized. */
function countWord(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** A day's activity as the readout says it: `7 reviews · 9 pages`. */
function activitySummary(cell: HeatmapCell): string {
  return `${countWord(cell.reviews, "review")} · ${countWord(cell.pages, "page")}`;
}

/** The floating readout: what a day holds, anchored over the cell it describes. */
type Tooltip = { summary: string; day: string; left: number; top: number };

/**
 * The week-aligned activity grid. Active days are shaded by their activity total
 * and carry a readout on hover *and* on keyboard focus; zero-activity days are
 * plain empty cells — no tooltip, no title, not focusable, nothing to answer for
 * (I-7). `today` is injectable for deterministic tests; it defaults to the current
 * instant.
 */
export function StudyHeatmap({
  days,
  today = new Date(),
}: {
  days: StudyDayView[];
  today?: Date;
}) {
  const cells = buildCells(days, today);
  const months = monthLabels(cells);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  const hideTooltip = useCallback(() => setTooltip(null), []);

  const showTooltip = useCallback((el: HTMLElement, cell: HeatmapCell) => {
    const rect = el.getBoundingClientRect();
    setTooltip({
      summary: activitySummary(cell),
      day: cell.label,
      left: rect.left + rect.width / 2,
      top: rect.top - 8,
    });
  }, []);

  // The readout is pinned to the viewport, so any scroll slides the cell out from
  // under it; it goes away rather than pointing at the wrong day. Capture picks up
  // scrolls in every container between the cell and the window.
  useEffect(() => {
    if (!tooltip) return;
    window.addEventListener("scroll", hideTooltip, true);
    return () => window.removeEventListener("scroll", hideTooltip, true);
  }, [tooltip, hideTooltip]);

  return (
    <div data-testid="study-heatmap" className="space-y-2">
      <div className="overflow-x-auto pb-0.5">
        <div
          role="group"
          aria-label={`study activity heatmap, last ${HEATMAP_WINDOW_WEEKS} weeks`}
          className="grid grid-cols-[auto_auto] justify-start gap-1.5"
        >
          <span aria-hidden />
          <div aria-hidden data-testid="heatmap-months" style={MONTHS_AXIS_STYLE}>
            {months.map((month) => (
              <span
                key={month.key}
                data-month-column={month.column}
                style={{ gridColumn: month.column }}
                className={`${AXIS_TEXT_CLASS} self-end whitespace-nowrap`}
              >
                {month.label}
              </span>
            ))}
          </div>
          <div
            aria-hidden
            data-testid="heatmap-weekdays"
            style={WEEKDAYS_AXIS_STYLE}
          >
            {WEEKDAYS.map((name, row) => (
              <span
                key={name}
                className={`${AXIS_TEXT_CLASS} text-right leading-[15px]`}
              >
                {WEEKDAY_LABEL_ROWS.includes(row) ? name : ""}
              </span>
            ))}
          </div>
          <div data-testid="heatmap-cells" style={CELLS_GRID_STYLE}>
            {cells.map((cell) => {
              if (cell.placeholder) {
                return (
                  <div
                    key={cell.key}
                    aria-hidden
                    data-placeholder
                    style={CELL_SIZE_STYLE}
                    className="rounded-[3px]"
                  />
                );
              }
              // Only a day with something on it answers to a pointer or the tab
              // key; an empty day is a shape, not a control (I-7).
              const active = cell.total > 0;
              return (
                <div
                  key={cell.key}
                  data-testid="heatmap-cell"
                  data-day={cell.day ?? undefined}
                  data-level={cell.level}
                  data-active={active ? "true" : undefined}
                  data-today={cell.today ? "true" : undefined}
                  role={active ? "img" : undefined}
                  aria-label={
                    active ? `${cell.label}: ${activitySummary(cell)}` : undefined
                  }
                  tabIndex={active ? 0 : undefined}
                  onMouseEnter={
                    active ? (e) => showTooltip(e.currentTarget, cell) : undefined
                  }
                  onMouseLeave={active ? hideTooltip : undefined}
                  onFocus={
                    active ? (e) => showTooltip(e.currentTarget, cell) : undefined
                  }
                  onBlur={active ? hideTooltip : undefined}
                  style={CELL_SIZE_STYLE}
                  className={`${CELL_BASE_CLASS} ${LEVEL_CLASS[cell.level]}${
                    cell.today ? " ring-1 ring-muted-foreground" : ""
                  }${
                    active
                      ? " outline-ring hover:outline-2 hover:outline-offset-1 focus-visible:outline-2 focus-visible:outline-offset-1"
                      : ""
                  }`}
                />
              );
            })}
          </div>
        </div>
      </div>

      <div
        className={`flex items-center justify-between gap-[18px] ${AXIS_TEXT_CLASS}`}
      >
        <span>Last {HEATMAP_WINDOW_WEEKS} weeks</span>
        <span data-testid="heatmap-legend" className="flex items-center gap-1">
          <span>Less</span>
          {LEVELS.map((level) => (
            <i
              key={level}
              aria-hidden
              data-legend-level={level}
              className={`block h-[11px] w-[11px] rounded-[2px] inset-ring-1 inset-ring-foreground/5 ${LEVEL_CLASS[level]}`}
            />
          ))}
          <span>More</span>
        </span>
      </div>

      {tooltip && (
        <div
          role="tooltip"
          aria-hidden
          data-testid="heatmap-tooltip"
          style={{
            position: "fixed",
            left: tooltip.left,
            top: tooltip.top,
            transform: "translate(-50%, -100%)",
            pointerEvents: "none",
            zIndex: 20,
          }}
          className="animate-in fade-in-0 rounded-[4px] bg-foreground px-[9px] py-1.5 font-mono text-[11.5px] leading-[1.45] whitespace-nowrap text-background shadow-lg motion-reduce:animate-none"
        >
          <span data-testid="tooltip-activity" className="block">
            {tooltip.summary}
          </span>
          <span data-testid="tooltip-day" className="block opacity-[0.68]">
            {tooltip.day}
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * The adherence figures, set in the approved tabular mono. The big number is the
 * server's `studied_last_14` and nothing else — wrapping it in a span changes how
 * it looks, never what it says, so the sentence still reads `Studied N of the last
 * 14 days` character for character (I-4).
 */
const FIGURE_CLASS =
  "font-mono text-[34px] leading-none font-medium tracking-[-0.03em] tabular-nums text-foreground";
const FIGURE_SM_CLASS = "font-mono text-[15px] tabular-nums text-foreground";
const TOTAL_VALUE_CLASS =
  "font-mono text-[17px] leading-[1.1] tabular-nums text-foreground";
const TOTAL_LABEL_CLASS =
  "font-mono text-[10.5px] tracking-[0.07em] text-muted-foreground uppercase";

/**
 * The readout above the graph: how many of the last fourteen days were studied,
 * and what the window added up to. The two totals are a plain sum of the rows the
 * graph is already showing — the adherence count beside them is never summed here,
 * it is the server's figure rendered as it arrived.
 */
function StudyReadout({ summary }: { summary: StudySummaryView }) {
  const reviews = summary.days.reduce((n, day) => n + day.reviews_count, 0);
  const pages = summary.days.reduce((n, day) => n + day.pages, 0);

  return (
    <div className="space-y-4">
      <p
        data-testid="streak-line"
        className="max-w-[22ch] text-sm leading-[1.35] text-muted-foreground"
      >
        Studied{" "}
        <span data-testid="adherence-figure" className={FIGURE_CLASS}>
          {summary.studied_last_14}
        </span>{" "}
        of the last <span className={FIGURE_SM_CLASS}>14</span> days
      </p>
      <div
        data-testid="study-totals"
        className="flex gap-[26px] border-t border-border pt-4"
      >
        <span data-testid="total-reviews" className="flex flex-col">
          <span className={TOTAL_VALUE_CLASS}>{reviews}</span>
          <span className={TOTAL_LABEL_CLASS}>reviews</span>
        </span>
        <span data-testid="total-pages" className="flex flex-col">
          <span className={TOTAL_VALUE_CLASS}>{pages}</span>
          <span className={TOTAL_LABEL_CLASS}>pages</span>
        </span>
      </div>
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
              <StudyReadout summary={state.data} />
              <StudyHeatmap days={state.data.days} />
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
