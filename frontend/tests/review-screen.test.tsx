// @vitest-environment jsdom

/**
 * E2 gate (component) — the review screen loads the due queue and drives one card
 * at a time: it shows the question only (a cloze keeps its `____` blank), Reveal
 * exposes the answer plus a citation footnote with an "Open in book" link to the
 * reader anchor, and a 4-button grade bar submits the FSRS rating and
 * auto-advances; after the last card a summary shows counts per rating
 * (QUIZ-19/QUIZ-15). Nothing due, a load failure (with retry), and a submit
 * failure (with retry) each settle to their own readable state.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ReviewScreen } from "../app/components/review-screen";
import { readUrl } from "../app/lib/read-url";

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

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

const clozeCard = {
  id: "i1",
  source_id: "s1",
  source_title: "Ready Book",
  item_type: "cloze",
  question: "Ada wrote the first ____.",
  answer: "algorithm",
  citation: {
    section_path: ["Chapter 1", "Core Idea"],
    anchor: "chapter-1.xhtml#core-idea",
    source_excerpt: "Ada wrote the first algorithm.",
  },
  provenance: null,
  status: "active",
  due: "2026-07-16T00:00:00Z",
};

const recallCard = {
  id: "i2",
  source_id: "s1",
  source_title: "Ready Book",
  item_type: "free_recall",
  question: "Who built the analytical engine?",
  answer: "Charles Babbage",
  citation: {
    section_path: ["Chapter 2"],
    anchor: "chapter-2.xhtml",
    source_excerpt: "Charles Babbage designed the analytical engine.",
  },
  provenance: null,
  status: "active",
  due: "2026-07-16T00:00:00Z",
};

const DUE = "/api/reviews/due";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReviewScreen session flow (E2)", () => {
  it("reveals a cloze card's answer + citation and links back into the reader", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, { items: [clozeCard], total_due: 1 }),
        "POST /api/quiz-items/i1/reviews": () =>
          jsonResponse(200, {
            state: 2,
            step: null,
            stability: 4,
            difficulty: 5,
            due: "2026-07-20T00:00:00Z",
            last_review: "2026-07-16T00:00:00Z",
          }),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);

    // Position and the question (with its cloze blank) show; the answer is hidden.
    const question = await screen.findByTestId("question");
    expect(question.textContent).toBe("Ada wrote the first ____.");
    expect(screen.getByTestId("position").textContent).toBe("1/1");
    expect(screen.queryByTestId("answer")).toBeNull();

    // Reveal exposes the answer and the citation footnote.
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByTestId("answer").textContent).toBe("algorithm");
    expect(screen.getByText("Chapter 1 › Core Idea")).toBeTruthy();
    expect(screen.getByText("Ada wrote the first algorithm.")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Open in book" }).getAttribute("href"),
    ).toBe(
      "/sources/s1/read?anchor=chapter-1.xhtml%23core-idea",
    );
  });

  it("filters the queue by source_id when the prop is set", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}?source_id=s1`]: () =>
        jsonResponse(200, { items: [clozeCard], total_due: 1 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen sourceId="s1" />);

    await screen.findByTestId("question");
    expect(
      fetchMock.mock.calls.some(([url]) => url === `${DUE}?source_id=s1`),
    ).toBe(true);
  });

  it("grades each card, advances, and shows counts per rating in the summary", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () =>
        jsonResponse(200, { items: [clozeCard, recallCard], total_due: 2 }),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, {
          state: 2,
          step: null,
          stability: 4,
          difficulty: 5,
          due: "2026-07-20T00:00:00Z",
          last_review: "2026-07-16T00:00:00Z",
        }),
      "POST /api/quiz-items/i2/reviews": () =>
        jsonResponse(200, {
          state: 1,
          step: 0,
          stability: null,
          difficulty: null,
          due: "2026-07-16T00:10:00Z",
          last_review: "2026-07-16T00:00:00Z",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);

    // Card 1 → Good (rating 3).
    await screen.findByTestId("question");
    expect(screen.getByTestId("position").textContent).toBe("1/2");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));

    // Advances to card 2, hidden again.
    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("2/2"),
    );
    expect(screen.getByTestId("question").textContent).toBe(
      "Who built the analytical engine?",
    );
    expect(screen.queryByTestId("answer")).toBeNull();

    // Card 2 → Again (rating 1).
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Again" }));

    // Summary: 2 reviewed, one Good and one Again.
    await screen.findByText("Session complete");
    expect(screen.getByTestId("reviewed-total").textContent).toContain("2");
    expect(screen.getByTestId("count-good").textContent).toBe("1");
    expect(screen.getByTestId("count-again").textContent).toBe("1");
    expect(screen.getByTestId("count-hard").textContent).toBe("0");
    expect(screen.getByTestId("count-easy").textContent).toBe("0");
    expect(
      screen.getByRole("link", { name: "Back to library" }).getAttribute("href"),
    ).toBe("/sources");
  });

  it("posts the chosen rating with a numeric review duration", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () =>
        jsonResponse(200, { items: [clozeCard], total_due: 1 }),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, {
          state: 2,
          step: null,
          stability: 4,
          difficulty: 5,
          due: "2026-07-20T00:00:00Z",
          last_review: "2026-07-16T00:00:00Z",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Easy" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) => url === "/api/quiz-items/i1/reviews",
        ),
      ).toBe(true),
    );
    const post = fetchMock.mock.calls.find(
      ([url]) => url === "/api/quiz-items/i1/reviews",
    )!;
    const body = JSON.parse((post[1] as RequestInit).body as string);
    expect(body.rating).toBe(4);
    expect(typeof body.review_duration_ms).toBe("number");
    expect(body.review_duration_ms).toBeGreaterThanOrEqual(0);
    expect(new Headers((post[1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );
  });

  it("shows a nothing-due empty state when the queue is empty", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () => jsonResponse(200, { items: [], total_due: 0 }),
      }),
    );

    render(<ReviewScreen />);

    expect(await screen.findByText(/nothing due/i)).toBeTruthy();
    expect(screen.queryByTestId("question")).toBeNull();
  });

  it("shows a readable load error with a retry that refetches the queue", async () => {
    let attempt = 0;
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse(500, { detail: "Boom." })
          : jsonResponse(200, { items: [clozeCard], total_due: 1 });
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Boom.");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    // The retry refetched and the queue now renders its first card.
    expect(await screen.findByTestId("question")).toBeTruthy();
  });

  it("shows a submit error with a retry affordance and keeps the card", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, { items: [clozeCard], total_due: 1 }),
        "POST /api/quiz-items/i1/reviews": () =>
          jsonResponse(429, { detail: "Too many requests." }),
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Too many requests.");
    // The card is retained (still on position 1/1, answer still revealed).
    expect(screen.getByTestId("position").textContent).toBe("1/1");
    expect(screen.getByTestId("answer")).toBeTruthy();
    // Dismissing the error via the retry affordance clears the banner.
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ReviewScreen auth (E2)", () => {
  it("does a UX-only redirect and shows the signed-out state when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<ReviewScreen onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});

describe("ReviewScreen pin and provenance (CAP-25/26/27)", () => {
  const highlightCard = {
    ...recallCard,
    id: "i3",
    provenance: { note_id: "n4", note_title: "Why Ada matters" },
  };

  it("renders the pin through readUrl so the reader route never drifts", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, { items: [clozeCard], total_due: 1 }),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // The href is exactly what the shared route builder produces for this card's
    // source and cited anchor — the hand-built URL is gone.
    expect(
      screen.getByRole("link", { name: "Open in book" }).getAttribute("href"),
    ).toBe(readUrl(clozeCard.source_id, clozeCard.citation.anchor));
  });

  it("offers the pin before the answer is revealed", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, { items: [clozeCard], total_due: 1 }),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // A failed card should become a re-read; that only works if the way back is
    // there while the answer is still hidden.
    expect(screen.queryByTestId("answer")).toBeNull();
    expect(screen.getByRole("link", { name: "Open in book" })).toBeTruthy();
  });

  it("shows the origin note's title for a card made at a passage", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, { items: [highlightCard], total_due: 1 }),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    const note = screen.getByTestId("card-provenance");
    expect(note.textContent).toContain("Why Ada matters");
    expect(note.getAttribute("href")).toBe("/notes/n4");
  });

  it("renders no note affordance for a card without provenance", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, { items: [clozeCard], total_due: 1 }),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // A deck card — or one whose origin note was deleted — has no note to offer,
    // and must not invent one. The pin itself still stands.
    expect(screen.queryByTestId("card-provenance")).toBeNull();
    expect(screen.getByRole("link", { name: "Open in book" })).toBeTruthy();
  });
});
