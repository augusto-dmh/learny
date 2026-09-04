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
  act,
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

const INTERVAL_LABELS = {
  "1": "~1m",
  "2": "~10m",
  "3": "~4d",
  "4": "~2w",
};

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
  note_changed: false,
  interval_labels: INTERVAL_LABELS,
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
  note_changed: false,
  interval_labels: INTERVAL_LABELS,
};

function dueQueue(
  items: unknown[],
  extra: Record<string, unknown> = {},
) {
  return {
    items,
    total_due: items.length,
    session_size: 20,
    requeue_minutes: 15,
    ...extra,
  };
}

function scheduling(due: string, extra: Record<string, unknown> = {}) {
  return {
    state: 2,
    step: null,
    stability: 4,
    difficulty: 5,
    due,
    last_review: "2026-07-16T00:00:00Z",
    interval_labels: INTERVAL_LABELS,
    ...extra,
  };
}

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
          jsonResponse(200, dueQueue([clozeCard])),
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
        jsonResponse(200, dueQueue([clozeCard])),
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
        jsonResponse(200, dueQueue([clozeCard, recallCard])),
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
        jsonResponse(200, dueQueue([clozeCard])),
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
        [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([])),
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
          : jsonResponse(200, dueQueue([clozeCard]));
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
          jsonResponse(200, dueQueue([clozeCard])),
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
          jsonResponse(200, dueQueue([clozeCard])),
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
          jsonResponse(200, dueQueue([clozeCard])),
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
          jsonResponse(200, dueQueue([highlightCard])),
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
          jsonResponse(200, dueQueue([clozeCard])),
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

describe("ReviewScreen note-changed badge and reset (NL-12/NL-13)", () => {
  const freshScheduling = {
    state: 1,
    step: 0,
    stability: null,
    difficulty: null,
    due: "2026-07-20T00:00:00Z",
    last_review: null,
  };

  const noteCard = {
    id: "i9",
    // A source-less note card (AD-149): no book to open, "Your notes" as its source.
    source_id: null,
    source_title: "Your notes",
    item_type: "free_recall",
    question: "What schedules reviews?",
    answer: "Spaced repetition",
    citation: {
      section_path: [],
      anchor: "",
      source_excerpt: "Spaced repetition schedules reviews",
    },
    provenance: { note_id: "n7", note_title: "How memory works" },
    status: "active",
    due: "2026-07-16T00:00:00Z",
    note_changed: true,
    interval_labels: INTERVAL_LABELS,
  };

  it("shows the badge linking the note, and offers no book pin for a note card", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([noteCard])),
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");

    // The "your note changed" badge is present and links the origin note (NL-12).
    const badge = screen.getByTestId("note-changed-badge");
    expect(badge.textContent).toContain("Your note changed");
    expect(badge.getAttribute("href")).toBe("/notes/n7");
    // A note card has no book, so the pin is absent — but its note provenance links
    // out (NL-13), reachable before reveal.
    expect(screen.queryByRole("link", { name: "Open in book" })).toBeNull();
    expect(screen.getByTestId("card-provenance").getAttribute("href")).toBe(
      "/notes/n7",
    );
  });

  it("hides the badge when the note has not changed since the card was seen", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([{ ...noteCard, note_changed: false }])),
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");

    expect(screen.queryByTestId("note-changed-badge")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reset schedule" })).toBeNull();
  });

  it("fires nothing when the reset confirm is declined", async () => {
    let resets = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([noteCard])),
        "POST /api/quiz-items/i9/schedule-reset": () => {
          resets += 1;
          return jsonResponse(200, freshScheduling);
        },
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");

    fireEvent.click(await screen.findByRole("button", { name: "Reset schedule" }));
    // The reset is confirm-gated: declining must not call the endpoint (NL-12).
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(resets).toBe(0);
    // The badge stands — nothing was reset.
    expect(screen.getByTestId("note-changed-badge")).toBeTruthy();
  });

  it("resets the schedule on explicit confirm and retires the badge", async () => {
    let resets = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([noteCard])),
        "POST /api/quiz-items/i9/schedule-reset": () => {
          resets += 1;
          return jsonResponse(200, freshScheduling);
        },
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");

    fireEvent.click(await screen.findByRole("button", { name: "Reset schedule" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm reset" }));

    // The endpoint fired exactly once and the badge retired to reflect the reset.
    await waitFor(() => expect(resets).toBe(1));
    await waitFor(() =>
      expect(screen.queryByTestId("note-changed-badge")).toBeNull(),
    );
    // The card stays on screen — a reset is a relearn, not a review, so it does not
    // advance the session.
    expect(screen.getByTestId("position").textContent).toBe("1/1");
  });
});

describe("ReviewScreen grading shortcuts (CAP-30/31/32)", () => {
  function pressKey(
    key: string,
    target: EventTarget = window,
    init: KeyboardEventInit = {},
  ) {
    act(() => {
      target.dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }),
      );
    });
  }

  function reviewFetch(onReview?: () => void) {
    return routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}?source_id=s1`]: () =>
        jsonResponse(200, dueQueue([clozeCard])),
      "POST /api/quiz-items/i1/reviews": () => {
        onReview?.();
        return jsonResponse(200, {
          state: 2,
          step: null,
          stability: 4,
          difficulty: 5,
          due: "2026-07-20T00:00:00Z",
          last_review: "2026-07-16T00:00:00Z",
        });
      },
    });
  }

  it("reveals the answer on the space bar", async () => {
    vi.stubGlobal("fetch", reviewFetch());

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    expect(screen.queryByTestId("answer")).toBeNull();

    pressKey(" ");

    await waitFor(
      () => expect(screen.getByTestId("answer").textContent).toBe("algorithm"),
      { timeout: 5000 },
    );
  });

  it("submits the pressed grade once the answer is revealed", async () => {
    const fetchMock = reviewFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));

    pressKey("3");

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url]) => url === "/api/quiz-items/i1/reviews",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string).rating).toBe(3);
    });
    // The session advanced past the only card, exactly as the button does.
    expect(await screen.findByTestId("reviewed-total")).toBeTruthy();
  });

  it("does not grade while the answer is still hidden", async () => {
    let reviews = 0;
    vi.stubGlobal("fetch", reviewFetch(() => (reviews += 1)));

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // A grade key before reveal would submit a self-assessment the student never
    // made — the binding set only carries the verb the card is offering.
    pressKey("1");
    pressKey("4");

    await waitFor(() => expect(screen.getByTestId("position")).toBeTruthy());
    expect(reviews).toBe(0);
  });

  it("ignores a grade key typed into a text field", async () => {
    let reviews = 0;
    vi.stubGlobal("fetch", reviewFetch(() => (reviews += 1)));

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));

    const input = document.body.appendChild(document.createElement("input"));
    pressKey("3", input);

    await waitFor(() => expect(screen.getByTestId("answer")).toBeTruthy());
    expect(reviews).toBe(0);
    input.remove();
  });

  it("ignores a grade key while a modifier is held", async () => {
    let reviews = 0;
    vi.stubGlobal("fetch", reviewFetch(() => (reviews += 1)));

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));

    pressKey("3", window, { metaKey: true });

    await waitFor(() => expect(screen.getByTestId("answer")).toBeTruthy());
    expect(reviews).toBe(0);
  });

  it("grades Good on Space once the answer is revealed (REV-44)", async () => {
    const fetchMock = reviewFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));

    pressKey(" ");

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url]) => url === "/api/quiz-items/i1/reviews",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string).rating).toBe(3);
    });
    expect(await screen.findByTestId("reviewed-total")).toBeTruthy();
  });

  it("still reveals on Space while the answer is hidden (REV-44)", async () => {
    let reviews = 0;
    vi.stubGlobal("fetch", reviewFetch(() => (reviews += 1)));

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");
    expect(screen.queryByTestId("answer")).toBeNull();

    pressKey(" ");

    expect(
      (await screen.findByTestId("answer", {}, { timeout: 5000 })).textContent,
    ).toBe("algorithm");
    expect(reviews).toBe(0);
  });
});

describe("ReviewScreen interval labels and requeue (REV-29/31/32)", () => {
  it("shows a bucketed next-interval label on each grade button", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([
            {
              ...clozeCard,
              interval_labels: { "1": "~1m", "2": "~10m", "3": "~1d", "4": "~4d" },
            },
          ])),
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));

    expect(screen.getByTestId("grade-interval-1").textContent).toBe("~1m");
    expect(screen.getByTestId("grade-interval-2").textContent).toBe("~10m");
    expect(screen.getByTestId("grade-interval-3").textContent).toBe("~1d");
    expect(screen.getByTestId("grade-interval-4").textContent).toBe("~4d");
  });

  it("requeues a ~1m due card into the remaining session without refetching the pile", async () => {
    const soon = new Date(Date.now() + 60 * 1000).toISOString();
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(
          200,
          scheduling(soon, {
            state: 1,
            step: 0,
            interval_labels: { "1": "~1m", "2": "~10m", "3": "~1d", "4": "~4d" },
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Again" }));

    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("2/2"),
    );
    expect(screen.queryByText("Session complete")).toBeNull();
    expect(screen.getByTestId("short-term-remaining").textContent).toMatch(
      /1 still in short-term review/,
    );
    expect(screen.queryByTestId("answer")).toBeNull();

    const dueGets = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).startsWith(DUE) &&
        ((init as RequestInit | undefined)?.method ?? "GET") === "GET",
    );
    expect(dueGets).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByTestId("grade-interval-3").textContent).toBe("~1d");
  });

  it("does not requeue a ~4d due card and does not show short-term remaining", async () => {
    const later = new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString();
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
      "POST /api/quiz-items/i1/reviews": () => jsonResponse(200, scheduling(later)),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Easy" }));

    expect(await screen.findByText("Session complete")).toBeTruthy();
    expect(screen.queryByTestId("short-term-remaining")).toBeNull();
    expect(screen.queryByTestId("question")).toBeNull();
  });
});

describe("ReviewScreen undo, flag, and edit (REV-22/37/45)", () => {
  function pressKey(
    key: string,
    target: EventTarget = window,
    init: KeyboardEventInit = {},
  ) {
    act(() => {
      target.dispatchEvent(
        new KeyboardEvent("keydown", {
          key,
          bubbles: true,
          cancelable: true,
          ...init,
        }),
      );
    });
  }

  it("restores the prior card as current when undo succeeds", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard, recallCard])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(
          200,
          scheduling(new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString()),
        ),
      "POST /api/reviews/undo": () =>
        jsonResponse(
          200,
          scheduling("2026-07-16T00:00:00Z", {
            interval_labels: { "1": "~1m", "2": "~10m", "3": "~1d", "4": "~4d" },
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toBe(
        "Who built the analytical engine?",
      ),
    );

    pressKey("u");

    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toBe(
        "Ada wrote the first ____.",
      ),
    );
    expect(screen.getByTestId("position").textContent).toBe("1/2");
    expect(
      fetchMock.mock.calls.some(([url]) => url === "/api/reviews/undo"),
    ).toBe(true);
  });

  it("undoes with Ctrl/Cmd+Z as well as u", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard, recallCard])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(
          200,
          scheduling(new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString()),
        ),
      "POST /api/reviews/undo": () => jsonResponse(200, scheduling("2026-07-16T00:00:00Z")),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toContain("analytical"),
    );

    pressKey("z", window, { metaKey: true });

    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toBe(
        "Ada wrote the first ____.",
      ),
    );
  });

  it("keeps a 409 empty-undo error visible on the current card", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
        "POST /api/reviews/undo": () =>
          jsonResponse(409, { detail: "Nothing to undo." }),
      }),
    );

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    pressKey("u");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Nothing to undo.");
    expect(screen.getByTestId("question").textContent).toBe(
      "Ada wrote the first ____.",
    );
    expect(screen.getByTestId("position").textContent).toBe("1/1");
  });

  it("flags the current card out of the local queue without submitting a review", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard, recallCard])),
      "POST /api/quiz-items/i1/flag": () =>
        jsonResponse(200, { flagged: true, flagged_at: "2026-09-04T00:00:00Z" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    expect((await screen.findByTestId("question")).textContent).toBe(
      "Ada wrote the first ____.",
    );
    expect(screen.getByTestId("position").textContent).toBe("1/2");

    pressKey("f");

    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toBe(
        "Who built the analytical engine?",
      ),
    );
    expect(screen.getByTestId("position").textContent).toBe("1/1");
    expect(
      fetchMock.mock.calls.some(([url]) => url === "/api/quiz-items/i1/flag"),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/reviews"),
      ),
    ).toBe(false);
  });

  it("edits question and answer in place without resetting the schedule", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
      "PATCH /api/quiz-items/i1": () =>
        jsonResponse(200, {
          id: "i1",
          question: "Ada wrote the first what?",
          answer: "computer program",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    pressKey("e");

    const questionField = await screen.findByTestId("edit-question");
    const answerField = screen.getByTestId("edit-answer");
    fireEvent.change(questionField, {
      target: { value: "Ada wrote the first what?" },
    });
    fireEvent.change(answerField, {
      target: { value: "computer program" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(screen.getByTestId("question").textContent).toBe(
        "Ada wrote the first what?",
      ),
    );
    expect(screen.getByTestId("position").textContent).toBe("1/1");
    expect(screen.queryByTestId("edit-question")).toBeNull();
    const patch = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/quiz-items/i1" &&
        (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patch).toBeTruthy();
    expect(JSON.parse((patch![1] as RequestInit).body as string)).toEqual({
      question: "Ada wrote the first what?",
      answer: "computer program",
    });
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("schedule-reset"),
      ),
    ).toBe(false);
  });
});
