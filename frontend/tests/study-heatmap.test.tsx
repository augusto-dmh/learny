// @vitest-environment jsdom

/**
 * T6 gate (component) — the adherence stats block (HOME-12/13/14, I-4/I-7).
 *
 * The streak line reads "Studied X of the last 14 days" straight from the server's
 * `studied_last_14`, never a client recomputation (I-4): the fixtures make that
 * count diverge from the day rows so a client that re-derived it would fail. The
 * heatmap renders the window as a grid where active days are shaded by their
 * activity total and zero-activity days are plain empty cells with no warning or
 * broken-streak affordance (HOME-13, I-7 silent grace). The hide toggle removes
 * the block and the choice survives a remount via localStorage, default shown
 * (HOME-14). A stats fetch failure shows a quiet inline error in the block.
 *
 * jsdom has no layout, so the week-aligned *visual* geometry (column/row
 * positioning, cell size) is not asserted here — only the grid's structure, cell
 * count, and per-cell activity level. Visual alignment is a recorded sensor-blind
 * note.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { StudyHeatmap, StudyStats } from "../app/components/study-heatmap";
import { HOME_SETTINGS_KEY } from "../app/components/use-home-settings";
import type { StudySummaryView } from "../app/lib/study";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Stub the global fetch to answer every study request with one response. */
function stubStudyFetch(response: Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response.clone()),
  );
}

const WARNING_TEXT = /missed|broken|streak|warning|lost/i;

describe("StudyHeatmap grid (HOME-13, I-7)", () => {
  // A fixed "today" makes the densified window deterministic without asserting
  // any pixel geometry (jsdom has no layout).
  const today = new Date(2026, 6, 20); // 2026-07-20 local

  const days = [
    { day: "2026-07-20", reviews_count: 2, reading_updates: 1 }, // total 3 → level 2
    { day: "2026-07-17", reviews_count: 1, reading_updates: 0 }, // total 1 → level 1
    { day: "2026-07-15", reviews_count: 4, reading_updates: 1 }, // total 5 → level 3
    { day: "2026-07-13", reviews_count: 5, reading_updates: 3 }, // total 8 → level 4
  ];

  it("renders the full window and shades active days by activity total", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    // The window is shown in full: one real cell per day (HOME-13).
    expect(container.querySelectorAll('[data-testid="heatmap-cell"]')).toHaveLength(
      84,
    );

    // Active days carry a non-zero shading level scaled by their total, across the
    // whole gradient — every non-zero level and both upper thresholds are pinned.
    expect(
      container.querySelector('[data-day="2026-07-20"]')?.getAttribute("data-level"),
    ).toBe("2");
    expect(
      container.querySelector('[data-day="2026-07-17"]')?.getAttribute("data-level"),
    ).toBe("1");
    expect(
      container.querySelector('[data-day="2026-07-15"]')?.getAttribute("data-level"),
    ).toBe("3");
    expect(
      container.querySelector('[data-day="2026-07-13"]')?.getAttribute("data-level"),
    ).toBe("4");
  });

  it("caps the shading at the top level and keeps the boundary totals distinct", () => {
    const boundaryDays = [
      { day: "2026-07-20", reviews_count: 6, reading_updates: 0 }, // total 6 → level 3 (top of band)
      { day: "2026-07-19", reviews_count: 7, reading_updates: 0 }, // total 7 → level 4
      { day: "2026-07-18", reviews_count: 40, reading_updates: 2 }, // total 42 → still level 4
    ];
    const { container } = render(<StudyHeatmap days={boundaryDays} today={today} />);

    expect(
      container.querySelector('[data-day="2026-07-20"]')?.getAttribute("data-level"),
    ).toBe("3");
    expect(
      container.querySelector('[data-day="2026-07-19"]')?.getAttribute("data-level"),
    ).toBe("4");
    expect(
      container.querySelector('[data-day="2026-07-18"]')?.getAttribute("data-level"),
    ).toBe("4");
  });

  it("leaves zero-activity days as plain empty cells with no warning affordance (silent grace)", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    // A day with no row is a level-0 cell with no title/tooltip messaging.
    const empty = container.querySelector('[data-day="2026-07-19"]');
    expect(empty?.getAttribute("data-level")).toBe("0");
    expect(empty?.getAttribute("title")).toBeNull();

    // No broken-streak / missed-day / warning language, and no status/alert role.
    expect(container.textContent ?? "").not.toMatch(WARNING_TEXT);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("StudyStats streak line (HOME-12, I-4)", () => {
  it("renders the adherence count from the server value, not a client recomputation", async () => {
    // Only one day row, but the server says 9 studied — a client that recomputed
    // from the rows would print 1.
    const summary: StudySummaryView = {
      days: [{ day: "2026-07-20", reviews_count: 1, reading_updates: 0 }],
      studied_last_14: 9,
    };
    stubStudyFetch(jsonResponse(200, summary));

    render(<StudyStats />);

    expect((await screen.findByTestId("streak-line")).textContent).toBe(
      "Studied 9 of the last 14 days",
    );
  });
});

describe("StudyStats new-user state (spec edge)", () => {
  it("reads 'Studied 0 of the last 14 days' with an all-empty heatmap", async () => {
    const summary: StudySummaryView = { days: [], studied_last_14: 0 };
    stubStudyFetch(jsonResponse(200, summary));

    const { container } = render(<StudyStats />);

    expect((await screen.findByTestId("streak-line")).textContent).toBe(
      "Studied 0 of the last 14 days",
    );
    const cells = container.querySelectorAll('[data-testid="heatmap-cell"]');
    expect(cells).toHaveLength(84);
    // Every day is empty — no shaded cell, no warning language (silent grace).
    for (const cell of cells) {
      expect(cell.getAttribute("data-level")).toBe("0");
    }
    expect(container.textContent ?? "").not.toMatch(WARNING_TEXT);
  });
});

describe("StudyStats hide toggle (HOME-14)", () => {
  it("shows the block by default, hides it on toggle, and keeps it hidden across a remount", async () => {
    stubStudyFetch(
      jsonResponse(200, { days: [], studied_last_14: 0 } satisfies StudySummaryView),
    );

    render(<StudyStats />);

    // Default: the block is visible.
    await screen.findByTestId("streak-line");
    expect(screen.getByTestId("study-heatmap")).toBeTruthy();

    // Toggling hide removes the streak line and heatmap...
    fireEvent.click(screen.getByRole("button", { name: "Hide stats" }));
    expect(screen.queryByTestId("streak-line")).toBeNull();
    expect(screen.queryByTestId("study-heatmap")).toBeNull();
    // ...and persists the choice device-locally.
    expect(JSON.parse(localStorage.getItem(HOME_SETTINGS_KEY)!)).toEqual({
      showStats: false,
    });

    // A remount (a reload) reads the stored choice: still hidden, toggle inverted.
    cleanup();
    render(<StudyStats />);
    expect(screen.getByRole("button", { name: "Show stats" })).toBeTruthy();
    await waitFor(() =>
      expect(screen.queryByTestId("study-heatmap")).toBeNull(),
    );
  });
});

describe("StudyStats fetch failure (spec edge)", () => {
  it("shows a quiet inline error when the study fetch fails", async () => {
    stubStudyFetch(jsonResponse(500, { detail: "Stats boom." }));

    render(<StudyStats />);

    expect((await screen.findByRole("alert")).textContent).toContain("Stats boom.");
    // The block failed quietly: no streak line or heatmap, no celebratory role.
    expect(screen.queryByTestId("streak-line")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
