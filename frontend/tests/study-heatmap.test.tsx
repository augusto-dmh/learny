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
  act,
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
    { day: "2026-07-20", reviews_count: 2, reading_updates: 1, pages: 9 }, // total 3 → level 2
    { day: "2026-07-17", reviews_count: 1, reading_updates: 0, pages: 0 }, // total 1 → level 1
    { day: "2026-07-15", reviews_count: 4, reading_updates: 1, pages: 1 }, // total 5 → level 3
    { day: "2026-07-13", reviews_count: 5, reading_updates: 3, pages: 24 }, // total 8 → level 4
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
      { day: "2026-07-20", reviews_count: 6, reading_updates: 0, pages: 0 }, // total 6 → level 3 (top of band)
      { day: "2026-07-19", reviews_count: 7, reading_updates: 0, pages: 0 }, // total 7 → level 4
      { day: "2026-07-18", reviews_count: 40, reading_updates: 2, pages: 0 }, // total 42 → still level 4
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

describe("StudyHeatmap layout (PAGE-19/20/21/23/26)", () => {
  const today = new Date(2026, 6, 20); // 2026-07-20 local, a Monday

  function graph() {
    const { container } = render(<StudyHeatmap days={[]} today={today} />);
    return container;
  }

  it("lays the cells on a fixed column track instead of stretching to the card", () => {
    const grid = graph().querySelector<HTMLElement>(
      '[data-testid="heatmap-cells"]',
    )!;

    // The defect was an implicit `auto` column track: seven rows were declared and
    // nothing constrained the columns, so they grew to the card's width.
    expect(grid.style.gridAutoFlow).toBe("column");
    expect(grid.style.gridAutoColumns).toBe("15px");
    expect(grid.style.gridAutoColumns).not.toBe("auto");
    expect(grid.style.gridTemplateRows).toBe("repeat(7, 15px)");
    expect(grid.style.gap).toBe("4px");
    // Start alignment is what keeps the block at its natural width.
    expect(grid.style.justifyContent).toBe("start");
  });

  it("hangs both axes off the same tracks as the cells", () => {
    const container = graph();
    const months = container.querySelector<HTMLElement>(
      '[data-testid="heatmap-months"]',
    )!;
    const weekdays = container.querySelector<HTMLElement>(
      '[data-testid="heatmap-weekdays"]',
    )!;

    // Month labels ride the cells' column track; weekday labels ride its row track.
    expect(months.style.gridAutoColumns).toBe("15px");
    expect(months.style.gap).toBe("4px");
    expect(weekdays.style.gridTemplateRows).toBe("repeat(7, 15px)");
    expect(weekdays.style.gap).toBe("4px");
  });

  it("names the weekday rows Mon/Wed/Fri and hides the axis from assistive tech", () => {
    const weekdays = graph().querySelector('[data-testid="heatmap-weekdays"]')!;
    const rows = [...weekdays.children].map((row) => row.textContent);

    // One entry per weekday row so the axis stays in step with the grid, with
    // every other row named (Sunday first, matching the grid's row order).
    expect(rows).toEqual(["", "Mon", "", "Wed", "", "Fri", ""]);
    expect(weekdays.getAttribute("aria-hidden")).toBe("true");
  });

  it("places each month's label over the column its first day lands in", () => {
    // The window ending 2026-07-20 opens on 2026-04-28, so the grid spans
    // April → July and each of the four months is named once.
    const months = graph().querySelector('[data-testid="heatmap-months"]')!;
    const labels = [...months.children].map((el) => [
      el.textContent,
      el.getAttribute("data-month-column"),
    ]);

    // Each month is named once, over the column holding its first day: April in
    // the opening column, then May, June, and July as each one starts.
    expect(labels).toEqual([
      ["Apr", "1"],
      ["May", "2"],
      ["Jun", "7"],
      ["Jul", "11"],
    ]);
  });

  it("does not label the final column, which has no column left to carry it", () => {
    // 2026-01-04 is a Sunday, so January opens the window's last column — a label
    // there would hang off the end of the axis, so it is dropped.
    const { container } = render(
      <StudyHeatmap days={[]} today={new Date(2026, 0, 4)} />,
    );
    const months = container.querySelector('[data-testid="heatmap-months"]')!;
    const cells = container.querySelectorAll('[data-testid="heatmap-cell"]');
    const columns =
      (cells.length + container.querySelectorAll("[data-placeholder]").length) / 7;

    expect([...months.children].map((el) => el.textContent)).toEqual([
      "Oct",
      "Nov",
      "Dec",
    ]);
    for (const label of months.children) {
      expect(Number(label.getAttribute("data-month-column"))).toBeLessThan(
        columns,
      );
    }
  });

  it("names the five levels with a Less→More key and labels the window", () => {
    const container = graph();
    const legend = container.querySelector('[data-testid="heatmap-legend"]')!;

    expect(legend.textContent).toBe("Less" + "More");
    expect(
      [...legend.querySelectorAll("[data-legend-level]")].map((el) =>
        el.getAttribute("data-legend-level"),
      ),
    ).toEqual(["0", "1", "2", "3", "4"]);
    // The window the graph covers is stated, not left to be counted.
    expect(container.textContent).toContain("Last 12 weeks");
  });

  it("rings today's cell and only today's", () => {
    const container = graph();
    const ringed = container.querySelectorAll('[data-today="true"]');

    expect(ringed).toHaveLength(1);
    expect(ringed[0].getAttribute("data-day")).toBe("2026-07-20");

    // The ring itself, not just the hook that marks it: "locatable" is the whole
    // point, so the visual treatment has to be asserted or it can be deleted
    // without anything noticing. Matched on the colour class because every cell
    // already carries `inset-ring-1` for its hairline edge.
    expect(ringed[0].className).toContain("ring-muted-foreground");
    const other = Array.from(
      container.querySelectorAll('[data-testid="heatmap-cell"]'),
    ).find((cell) => cell.getAttribute("data-day") !== "2026-07-20")!;
    expect(other.className).not.toContain("ring-muted-foreground");
  });

  it("gives real cells a hairline edge and leaves placeholders blank", () => {
    const container = graph();
    const cell = container.querySelector('[data-testid="heatmap-cell"]')!;
    const placeholder = container.querySelector("[data-placeholder]")!;

    // An unshaded day still has definition; a week-alignment placeholder has none.
    expect(cell.className).toContain("inset-ring");
    expect(placeholder.className).not.toContain("inset-ring");
    expect(placeholder.className).not.toContain("bg-");
  });

  it("keeps the existing test hooks and the 84-day window", () => {
    const container = graph();

    expect(screen.getByTestId("study-heatmap")).toBeTruthy();
    expect(container.querySelectorAll('[data-testid="heatmap-cell"]')).toHaveLength(
      84,
    );
    for (const cell of container.querySelectorAll('[data-testid="heatmap-cell"]')) {
      expect(cell.getAttribute("data-day")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(cell.getAttribute("data-level")).toBe("0");
    }
    expect(
      container.querySelectorAll("[data-placeholder]").length,
    ).toBeGreaterThan(0);
  });
});

describe("StudyHeatmap tooltip (PAGE-22, I-7)", () => {
  const today = new Date(2026, 6, 20); // 2026-07-20 local, a Monday

  // One busy day, one single-count day (to pin pluralization), and a day whose
  // pages figure is nothing like its activity total — a client deriving pages from
  // the counters, or from a words-per-page constant of its own, would disagree.
  const days = [
    { day: "2026-07-20", reviews_count: 7, reading_updates: 2, pages: 9 },
    { day: "2026-07-14", reviews_count: 1, reading_updates: 0, pages: 1 },
  ];

  function cellFor(container: HTMLElement, day: string) {
    return container.querySelector<HTMLElement>(`[data-day="${day}"]`)!;
  }

  it("shows the day's reviews, pages, and date on hover", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    expect(screen.queryByTestId("heatmap-tooltip")).toBeNull();
    fireEvent.mouseEnter(cellFor(container, "2026-07-20"));

    expect(screen.getByTestId("tooltip-activity").textContent).toBe(
      "7 reviews · 9 pages",
    );
    expect(screen.getByTestId("tooltip-day").textContent).toBe("Mon, Jul 20");
  });

  it("shows the same readout on keyboard focus, not only on hover", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);
    const cell = cellFor(container, "2026-07-20");

    // The cell is reachable by tab, and reaching it says what the day holds.
    expect(cell.getAttribute("tabindex")).toBe("0");
    fireEvent.focus(cell);

    expect(screen.getByTestId("tooltip-activity").textContent).toBe(
      "7 reviews · 9 pages",
    );
    expect(screen.getByTestId("tooltip-day").textContent).toBe("Mon, Jul 20");
  });

  it("counts of one read in the singular", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    fireEvent.mouseEnter(cellFor(container, "2026-07-14"));

    expect(screen.getByTestId("tooltip-activity").textContent).toBe(
      "1 review · 1 page",
    );
  });

  it("takes the readout away on mouse leave, on blur, and on scroll", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);
    const cell = cellFor(container, "2026-07-20");

    fireEvent.mouseEnter(cell);
    fireEvent.mouseLeave(cell);
    expect(screen.queryByTestId("heatmap-tooltip")).toBeNull();

    fireEvent.focus(cell);
    fireEvent.blur(cell);
    expect(screen.queryByTestId("heatmap-tooltip")).toBeNull();

    // A scroll slides the cell out from under a viewport-pinned readout.
    fireEvent.focus(cell);
    expect(screen.getByTestId("heatmap-tooltip")).toBeTruthy();
    fireEvent.scroll(window);
    expect(screen.queryByTestId("heatmap-tooltip")).toBeNull();
  });

  it("leaves empty days silent: no readout, no title, and no way to focus one", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);
    const empty = cellFor(container, "2026-07-19");

    expect(empty.getAttribute("data-level")).toBe("0");
    expect(empty.getAttribute("title")).toBeNull();
    expect(empty.getAttribute("tabindex")).toBeNull();
    expect(empty.getAttribute("data-active")).toBeNull();
    expect(empty.getAttribute("aria-label")).toBeNull();

    // Hovering one says nothing at all — there is nothing to answer for (I-7).
    fireEvent.mouseEnter(empty);
    expect(screen.queryByTestId("heatmap-tooltip")).toBeNull();
    expect(container.textContent ?? "").not.toMatch(WARNING_TEXT);
  });

  it("keeps the readout out of the tab order and off the focused cell", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);
    const cell = cellFor(container, "2026-07-20");

    act(() => cell.focus());
    const tooltip = screen.getByTestId("heatmap-tooltip");

    // Decoration, not a stop: the cell keeps focus and the readout can't take it.
    expect(document.activeElement).toBe(cell);
    expect(tooltip.getAttribute("aria-hidden")).toBe("true");
    expect(tooltip.querySelector("[tabindex]")).toBeNull();
    expect(tooltip.getAttribute("tabindex")).toBeNull();
  });

  it("carries the pages the server sent without touching any cell's shading", () => {
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    // 7 + 2 = 9 activity → level 4; the day's 9 pages leave that untouched, and
    // the 1-review day stays level 1 despite its own page count.
    expect(cellFor(container, "2026-07-20").getAttribute("data-level")).toBe("4");
    expect(cellFor(container, "2026-07-14").getAttribute("data-level")).toBe("1");

    // And the figure shown is the server's, not one derived from the counters.
    fireEvent.mouseEnter(cellFor(container, "2026-07-20"));
    expect(screen.getByTestId("tooltip-activity").textContent).toContain(
      "9 pages",
    );
  });
});

describe("StudyStats streak line (HOME-12, I-4)", () => {
  it("renders the adherence count from the server value, not a client recomputation", async () => {
    // Only one day row, but the server says 9 studied — a client that recomputed
    // from the rows would print 1.
    const summary: StudySummaryView = {
      days: [
        { day: "2026-07-20", reviews_count: 1, reading_updates: 0, pages: 3 },
      ],
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

describe("StudyStats readout (PAGE-24/25, I-PU-8)", () => {
  // The pages figures are deliberately unrelated to the counters: a readout that
  // derived pages from activity, or from a quantum of its own, would disagree.
  const summary: StudySummaryView = {
    days: [
      { day: "2026-07-20", reviews_count: 7, reading_updates: 2, pages: 9 },
      { day: "2026-07-19", reviews_count: 3, reading_updates: 1, pages: 24 },
      { day: "2026-07-18", reviews_count: 0, reading_updates: 2, pages: 7 },
    ],
    studied_last_14: 11,
  };

  it("sets the adherence figures in tabular mono without touching the sentence", async () => {
    stubStudyFetch(jsonResponse(200, summary));

    render(<StudyStats />);

    // The styling wraps the digits; the sentence reads exactly as it always has.
    expect((await screen.findByTestId("streak-line")).textContent).toBe(
      "Studied 11 of the last 14 days",
    );
    const figure = screen.getByTestId("adherence-figure");
    expect(figure.textContent).toBe("11");
    expect(figure.className).toContain("font-mono");
    expect(figure.className).toContain("tabular-nums");
  });

  it("totals the window's reviews and its pages beside the adherence figure", async () => {
    stubStudyFetch(jsonResponse(200, summary));

    render(<StudyStats />);
    await screen.findByTestId("streak-line");

    // 7 + 3 + 0 reviews, and the server's 9 + 24 + 7 pages.
    const reviews = screen.getByTestId("total-reviews");
    expect(reviews.children[0].textContent).toBe("10");
    expect(reviews.children[1].textContent).toBe("reviews");
    const pages = screen.getByTestId("total-pages");
    expect(pages.children[0].textContent).toBe("40");
    expect(pages.children[1].textContent).toBe("pages");
  });

  it("reads zero for both totals when the window is empty, and says nothing more", async () => {
    stubStudyFetch(
      jsonResponse(200, { days: [], studied_last_14: 0 } satisfies StudySummaryView),
    );

    const { container } = render(<StudyStats />);
    await screen.findByTestId("streak-line");

    expect(screen.getByTestId("total-reviews").children[0].textContent).toBe("0");
    expect(screen.getByTestId("total-pages").children[0].textContent).toBe("0");
    // A new user's empty window is stated plainly — no encouragement, no warning.
    expect(container.textContent ?? "").not.toMatch(WARNING_TEXT);
    expect(screen.queryByRole("status")).toBeNull();
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
