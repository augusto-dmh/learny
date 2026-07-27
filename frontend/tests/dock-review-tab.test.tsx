// @vitest-environment jsdom

/**
 * The dock's Review tab (WSN-06/07) — what this book has waiting, graded in place.
 *
 * The reader is on the page; reviewing what they read there should not cost them
 * the page. So the tab says how many cards are due from this book and then hands
 * the reader the shipped review screen, scoped to the book — the same reveal, the
 * same grade bar, the same submit — rather than a link somewhere else or a second
 * grading UI built for a narrow column.
 *
 * The figure is inventory: a queue length and nothing more. A book with nothing
 * due says so and offers no grading, and no surface here congratulates, warns, or
 * counts days.
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

import { ReaderPanel } from "../app/components/reader-panel";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

vi.mock("../app/components/ask-panel", () => ({
  AskPanel: () => <div data-testid="ask-panel-body" />,
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: () => <div data-testid="teach-panel-body" />,
}));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const authedMe = {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
};

function card(id: string, question: string, answer: string) {
  return {
    id,
    source_id: "s1",
    source_title: "Ready Book",
    item_type: "free_recall",
    question,
    answer,
    citation: {
      section_path: ["Chapter 1", "Core Idea"],
      anchor: "chapter-1.xhtml#core-idea",
      source_excerpt: "Ada wrote the first algorithm.",
    },
    provenance: null,
    status: "active",
    due: "2026-07-16T00:00:00Z",
    note_changed: false,
  };
}

/**
 * The dock against a book with `cards` due. Every other request the dock makes
 * settles empty; anything unrouted fails loudly.
 */
function stubBook(cards: ReturnType<typeof card>[]) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/auth/me") {
      return jsonResponse(200, authedMe);
    }
    if (url.startsWith("/api/notes")) {
      return jsonResponse(200, []);
    }
    if (url.startsWith("/api/reviews/due")) {
      return jsonResponse(200, { items: cards, total_due: cards.length });
    }
    if (init?.method === "POST" && url.startsWith("/api/quiz-items/")) {
      return jsonResponse(200, { state: 2, step: null, due: "later" });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderReviewTab() {
  return render(
    <ReaderPanel
      sourceId="s1"
      csrf="csrf-xyz"
      tab="review"
      onTabChange={() => {}}
      onClose={() => {}}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("the dock's Review tab", () => {
  it("says how many cards this book has waiting, on the tab and in the panel", async () => {
    stubBook([
      card("i1", "Who wrote the first algorithm?", "Ada Lovelace"),
      card("i2", "Who built the analytical engine?", "Charles Babbage"),
      card("i3", "What is a cloze?", "A blanked sentence"),
    ]);
    renderReviewTab();

    expect((await screen.findByTestId("due-count")).textContent).toBe("3");
    expect(screen.getByText("cards due from this book")).toBeTruthy();
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: /^Review/ }).textContent?.trim(),
      ).toBe("Review3"),
    );
  });

  it("re-reads the book's due count once a card has been graded", async () => {
    // The queue is drained inside the dock, right beside the count — so unlike a
    // whole-page review, the figure is on screen while it goes stale. The server's
    // total drops as the card leaves the queue.
    const cards = [
      card("i1", "Who wrote the first algorithm?", "Ada Lovelace"),
      card("i2", "Who built the analytical engine?", "Charles Babbage"),
    ];
    let remaining = cards.length;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/auth/me") return jsonResponse(200, authedMe);
      if (url.startsWith("/api/notes")) return jsonResponse(200, []);
      if (url.startsWith("/api/reviews/due")) {
        return jsonResponse(200, { items: cards, total_due: remaining });
      }
      if (init?.method === "POST" && url.startsWith("/api/quiz-items/")) {
        remaining -= 1;
        return jsonResponse(200, { state: 2, step: null, due: "later" });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderReviewTab();

    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: /^Review/ }).textContent?.trim(),
      ).toBe("Review2"),
    );

    await screen.findByText("Who wrote the first algorithm?");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Good" }));
    });

    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: /^Review/ }).textContent?.trim(),
      ).toBe("Review1"),
    );
    expect(screen.getByTestId("due-count").textContent).toBe("1");
  });

  it("grades a card in the dock, with the book's page never left behind", async () => {
    const fetchMock = stubBook([
      card("i1", "Who wrote the first algorithm?", "Ada Lovelace"),
      card("i2", "Who built the analytical engine?", "Charles Babbage"),
    ]);
    renderReviewTab();

    // The grading is the shipped flow: reveal, then grade.
    await screen.findByText("Who wrote the first algorithm?");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByTestId("answer").textContent).toBe("Ada Lovelace");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Good" }));
    });

    // The grade reached the server and the queue advanced — all inside the dock,
    // which is still the dock: the reader was never navigated away from it.
    const graded = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).startsWith("/api/quiz-items/") &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(graded?.[0]).toBe("/api/quiz-items/i1/reviews");
    expect(screen.getByTestId("position").textContent).toBe("2/2");
    expect(screen.getByTestId("reader-panel")).toBeTruthy();
  });

  it("offers no grading when this book has nothing due", async () => {
    stubBook([]);
    renderReviewTab();

    expect(
      await screen.findByText("Nothing due from this book right now."),
    ).toBeTruthy();
    expect(screen.queryByTestId("due-count")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reveal answer" })).toBeNull();
    // Nothing due is nothing due — not a zero on the tab.
    expect(
      screen.getByRole("tab", { name: /^Review/ }).textContent?.trim(),
    ).toBe("Review");
  });

  it("counts the queue and nothing else — no streak, badge, or reproach", async () => {
    stubBook([card("i1", "Who wrote the first algorithm?", "Ada Lovelace")]);
    renderReviewTab();

    await screen.findByTestId("due-count");
    const dock = screen.getByTestId("reader-panel").textContent ?? "";
    expect(dock).not.toMatch(
      /streak|behind|catch up|keep it up|in a row|don.t break|badge|well done/i,
    );
  });

  it("says so when what is due cannot be loaded", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.startsWith("/api/reviews/due")) {
        return jsonResponse(500, { detail: "Could not reach the scheduler." });
      }
      return jsonResponse(200, url === "/api/auth/me" ? authedMe : []);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderReviewTab();

    expect((await screen.findAllByRole("alert"))[0].textContent).toBe(
      "Could not reach the scheduler.",
    );
  });
});
