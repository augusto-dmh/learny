// @vitest-environment jsdom

/**
 * T5 gate (component) — the two-card Home (HOME-02/03/05/06 + isolation edge case).
 *
 * The hero renders the book/chapter/percent with a resume link into
 * `/sources/{id}/read` (HOME-03), and its null empty-shape becomes a pick-a-book
 * state linking the bookshelf (HOME-02). The due card shows the count with a
 * review CTA when cards are due (HOME-05) and a calm done-for-today state — no
 * count, CTA, or celebratory affordance — at zero (HOME-06, I-7). The two fetches
 * are independent: one failing renders that card's quiet error while the other
 * still renders its data (spec edge case). A brand-new user (null hero + zero due)
 * shows both empty states at once (spec edge case).
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { HomeScreen } from "../app/components/home-screen";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const CONTINUE = "GET /api/reading/continue";
const DUE = "GET /api/reviews/due?limit=1";

const hero = {
  source_id: "s1",
  source_title: "Ready Book",
  chapter_title: "Chapter One",
  percent: 42.5,
  updated_at: "2026-07-19T00:00:00Z",
};

function dueQueue(total: number) {
  return { items: [], total_due: total };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ContinueHero (HOME-02/03)", () => {
  it("renders book, chapter, and percent with a resume link into the reader", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, hero),
        [DUE]: () => jsonResponse(200, dueQueue(0)),
      }),
    );

    render(<HomeScreen />);

    expect((await screen.findByTestId("hero-title")).textContent).toBe(
      "Ready Book",
    );
    expect(screen.getByTestId("hero-chapter").textContent).toBe("Chapter One");
    // 42.5 rounds to 43 for display.
    expect(screen.getByTestId("hero-percent").textContent).toBe("43% read");
    // Resume relies on the reader's existing resume path: no anchor query.
    expect(
      screen.getByRole("link", { name: "Resume" }).getAttribute("href"),
    ).toBe("/sources/s1/read");
  });

  it("shows a pick-a-book empty state linking the bookshelf when nothing is in progress (HOME-02)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, null),
        [DUE]: () => jsonResponse(200, dueQueue(3)),
      }),
    );

    render(<HomeScreen />);

    const link = await screen.findByRole("link", { name: "Pick a book" });
    expect(link.getAttribute("href")).toBe("/sources");
    // The empty hero shows no resume affordance and no fabricated book.
    expect(screen.queryByTestId("hero-title")).toBeNull();
    expect(screen.queryByRole("link", { name: "Resume" })).toBeNull();
  });
});

describe("DueCard (HOME-05/06)", () => {
  it("shows the due count and a review CTA when cards are due", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, hero),
        [DUE]: () => jsonResponse(200, dueQueue(5)),
      }),
    );

    render(<HomeScreen />);

    const count = await screen.findByTestId("due-count");
    expect(count.textContent).toContain("5");
    expect(
      screen.getByRole("link", { name: "Review" }).getAttribute("href"),
    ).toBe("/review");
  });

  it("shows a calm done-for-today state with no count, CTA, or celebration at zero due (HOME-06, I-7)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, hero),
        [DUE]: () => jsonResponse(200, dueQueue(0)),
      }),
    );

    render(<HomeScreen />);

    expect(await screen.findByTestId("due-done")).toBeTruthy();
    // No count, no review CTA, and — the gamification cap — no badge/status role
    // that would read as a celebratory affordance.
    expect(screen.queryByTestId("due-count")).toBeNull();
    expect(screen.queryByRole("link", { name: "Review" })).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("HomeScreen fetch isolation (spec edge case)", () => {
  it("renders the due card when the hero fetch fails, without blanking it", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(500, { detail: "Hero boom." }),
        [DUE]: () => jsonResponse(200, dueQueue(5)),
      }),
    );

    render(<HomeScreen />);

    // The hero shows its own quiet error…
    expect((await screen.findByRole("alert")).textContent).toContain("Hero boom.");
    // …while the due card still renders its data.
    expect((await screen.findByTestId("due-count")).textContent).toContain("5");
  });

  it("renders the hero when the due fetch fails, without blanking it", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, hero),
        [DUE]: () => jsonResponse(500, { detail: "Due boom." }),
      }),
    );

    render(<HomeScreen />);

    // The hero still renders its book…
    expect((await screen.findByTestId("hero-title")).textContent).toBe(
      "Ready Book",
    );
    // …while the due card shows its own quiet error.
    expect((await screen.findByRole("alert")).textContent).toContain("Due boom.");
  });
});

describe("HomeScreen new-user state (spec edge case)", () => {
  it("shows the pick-a-book hero and the done-for-today card together", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [CONTINUE]: () => jsonResponse(200, null),
        [DUE]: () => jsonResponse(200, dueQueue(0)),
      }),
    );

    render(<HomeScreen />);

    expect(
      (await screen.findByRole("link", { name: "Pick a book" })).getAttribute(
        "href",
      ),
    ).toBe("/sources");
    await waitFor(() => expect(screen.getByTestId("due-done")).toBeTruthy());
  });
});
