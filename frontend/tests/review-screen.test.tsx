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

import ReviewPage from "../app/(app)/review/page";
import { ReviewScreen } from "../app/components/review-screen";
import { StudyHeatmap, StudyStats } from "../app/components/study-heatmap";
import { readUrl } from "../app/lib/read-url";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

// `suspend` holds the review page on its Suspense fallback.
const nav = vi.hoisted(() => ({ suspend: false }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => {
    if (nav.suspend) {
      throw new Promise(() => {});
    }
    return new URLSearchParams();
  },
}));

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
    if (!handler && key === "GET /api/sources") {
      return jsonResponse(200, []);
    }
    if (!handler && /^POST \/api\/sources\/[^/]+\/quiz\/starter$/.test(key)) {
      return jsonResponse(200, { items: [] });
    }
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

  it("clones starter cards for the sample before loading due", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () =>
        jsonResponse(200, [
          {
            id: "s-sample",
            title: "The Art of War",
            filename: "art-of-war.epub",
            byte_size: 3,
            content_type: "application/epub+zip",
            status: "ready",
            created_at: "now",
            is_sample: true,
            suggested_question: "What does Sun Tzu mean by deception?",
          },
        ]),
      "POST /api/sources/s-sample/quiz/starter": () =>
        jsonResponse(200, { items: [] }),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);

    await screen.findByTestId("question");
    const urls = fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${url}`);
    expect(urls).toContain("POST /api/sources/s-sample/quiz/starter");
    const starterIdx = urls.indexOf("POST /api/sources/s-sample/quiz/starter");
    const dueIdx = urls.indexOf(`GET ${DUE}`);
    expect(starterIdx).toBeGreaterThan(-1);
    expect(dueIdx).toBeGreaterThan(starterIdx);
    const starterCall = fetchMock.mock.calls[starterIdx];
    expect(new Headers(starterCall[1]?.headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );
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

    // A 5xx reads as the shared server copy; the backend detail stays data.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The server had a problem. Please try again.");
    expect(alert.textContent).not.toContain("Boom.");

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

  it("undoes a short-term requeue without refetching the pile", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "Again" }));
    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("2/2"),
    );

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "u", bubbles: true, cancelable: true }),
      );
    });

    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("1/1"),
    );
    expect(screen.getByTestId("question").textContent).toBe(
      "Ada wrote the first ____.",
    );
    expect(screen.queryByTestId("short-term-remaining")).toBeNull();
    expect(
      fetchMock.mock.calls.some(([url]) => url === "/api/reviews/undo"),
    ).toBe(true);
    const dueGets = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).startsWith(DUE) &&
        ((init as RequestInit | undefined)?.method ?? "GET") === "GET",
    );
    expect(dueGets).toHaveLength(1);
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

    // The undo operation's copy, never the backend detail.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Could not undo your last review.");
    expect(alert.textContent).not.toContain("Nothing to undo.");
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
    // Under load the keypress can land in the window where the shortcut handlers
    // are being re-attached, so retry it until the editor is open instead of
    // firing once and hoping. Pressing "e" again is safe: startEdit is
    // idempotent and the shortcuts unmount while the editor is open.
    await waitFor(() => {
      pressKey("e");
      return expect(screen.queryByTestId("edit-question")).not.toBeNull();
    });
    const questionField = screen.getByTestId("edit-question");
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

  it("confidence buttons reveal the answer beside Reveal answer", async () => {
    const third = { ...recallCard, id: "i3", question: "What is spaced repetition?" };
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}?source_id=s1`]: () =>
          jsonResponse(200, dueQueue([clozeCard, recallCard, third])),
        "POST /api/quiz-items/i1/reviews": () =>
          jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
        "POST /api/quiz-items/i2/reviews": () =>
          jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
        "POST /api/quiz-items/i3/reviews": () =>
          jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
      }),
    );

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // While hidden, the card offers the three confidence buttons beside Reveal
    // answer, and the answer itself stays hidden.
    const group = screen.getByRole("group", { name: "How sure were you?" });
    expect([...group.querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "Not sure",
      "Fairly sure",
      "Sure",
    ]);
    expect(screen.getByRole("button", { name: "Reveal answer" })).toBeTruthy();
    expect(screen.queryByTestId("answer")).toBeNull();

    // Each confidence button reveals the answer; grading moves to the next card.
    fireEvent.click(screen.getByRole("button", { name: "Not sure" }));
    expect(screen.getByTestId("answer").textContent).toBe("algorithm");
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await screen.findByText("Who built the analytical engine?");
    fireEvent.click(screen.getByRole("button", { name: "Fairly sure" }));
    expect(screen.getByTestId("answer").textContent).toBe("Charles Babbage");
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await screen.findByText("What is spaced repetition?");
    fireEvent.click(screen.getByRole("button", { name: "Sure" }));
    expect(screen.getByTestId("answer").textContent).toBe("Charles Babbage");
  });

  it("grade carries confidence only when revealed by a confidence tap", async () => {
    const third = { ...recallCard, id: "i3", question: "What is spaced repetition?" };
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}?source_id=s1`]: () =>
        jsonResponse(200, dueQueue([clozeCard, recallCard, third])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
      "POST /api/quiz-items/i2/reviews": () =>
        jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
      "POST /api/quiz-items/i3/reviews": () =>
        jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
    });
    vi.stubGlobal("fetch", fetchMock);

    const bodyOf = (url: string) => {
      const call = fetchMock.mock.calls.find(
        ([called, init]) =>
          called === url && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(call).toBeTruthy();
      return JSON.parse((call![1] as RequestInit).body as string);
    };

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // A grade after a confidence tap sends that confidence.
    fireEvent.click(screen.getByRole("button", { name: "Sure" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() => expect(bodyOf("/api/quiz-items/i1/reviews").rating).toBe(3));
    expect(bodyOf("/api/quiz-items/i1/reviews").confidence).toBe(3);
    expect(bodyOf("/api/quiz-items/i1/reviews").assisted).toBe(false);

    // Grading after Reveal answer sends a body with no confidence key at all.
    await screen.findByText("Who built the analytical engine?");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() => expect(bodyOf("/api/quiz-items/i2/reviews").rating).toBe(3));
    expect("confidence" in bodyOf("/api/quiz-items/i2/reviews")).toBe(false);

    // Space reveals without a confidence tap: no confidence key either.
    await screen.findByText("What is spaced repetition?");
    pressKey(" ");
    await waitFor(() => expect(screen.getByTestId("answer")).toBeTruthy());
    pressKey("3");
    await waitFor(() => expect(bodyOf("/api/quiz-items/i3/reviews").rating).toBe(3));
    expect("confidence" in bodyOf("/api/quiz-items/i3/reviews")).toBe(false);
  });

  it("editor peek before reveal marks the grade assisted", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}?source_id=s1`]: () =>
        jsonResponse(200, dueQueue([clozeCard, recallCard])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
      "POST /api/quiz-items/i2/reviews": () =>
        jsonResponse(200, scheduling("2026-07-20T00:00:00Z")),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // The editor shows the answer beside the question, so opening it before the
    // reveal is seeing the answer: the grade is recorded as assisted.
    await waitFor(() => {
      pressKey("e");
      return expect(screen.queryByTestId("edit-question")).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => url === "/api/quiz-items/i1/reviews");
      expect(call).toBeTruthy();
      const body = JSON.parse((call![1] as RequestInit).body as string);
      expect(body.rating).toBe(3);
      expect(body.assisted).toBe(true);
    });

    // Grading without ever opening the editor stays unaided.
    await screen.findByText("Who built the analytical engine?");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => url === "/api/quiz-items/i2/reviews");
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string).assisted).toBe(false);
    });
  });
});

describe("ReviewScreen Done-for-today (REV-42/43)", () => {
  const continueHero = {
    source_id: "s1",
    source_title: "Ready Book",
    chapter_title: "Chapter One",
    percent: 42.5,
    updated_at: "2026-07-19T00:00:00Z",
  };

  const later = () =>
    new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString();

  it("offers Keep going and the continue-reading book when due remains after the session page", async () => {
    let duePage = 0;
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => {
        duePage += 1;
        return duePage === 1
          ? jsonResponse(200, dueQueue([clozeCard], { total_due: 3 }))
          : jsonResponse(200, dueQueue([recallCard], { total_due: 2 }));
      },
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, scheduling(later())),
      "GET /api/reading/continue": () => jsonResponse(200, continueHero),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));

    expect(await screen.findByTestId("done-for-today")).toBeTruthy();
    expect(screen.queryByText("Session complete")).toBeNull();
    expect(screen.getByRole("button", { name: "Keep going" })).toBeTruthy();
    const book = await screen.findByTestId("continue-reading");
    expect(book.getAttribute("href")).toBe("/sources/s1/read");
    expect(book.textContent).toContain("Ready Book");

    const dueGetsBefore = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).startsWith(DUE) &&
        ((init as RequestInit | undefined)?.method ?? "GET") === "GET",
    );
    expect(dueGetsBefore).toHaveLength(1);
    expect(String(dueGetsBefore[0][0])).not.toMatch(/limit=/);

    fireEvent.click(screen.getByRole("button", { name: "Keep going" }));

    expect(await screen.findByTestId("question")).toBeTruthy();
    expect(screen.getByTestId("question").textContent).toBe(
      "Who built the analytical engine?",
    );
    expect(screen.queryByTestId("done-for-today")).toBeNull();
    expect(screen.queryByRole("button", { name: "Keep going" })).toBeNull();

    const dueGets = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).startsWith(DUE) &&
        ((init as RequestInit | undefined)?.method ?? "GET") === "GET",
    );
    expect(dueGets).toHaveLength(2);
    expect(dueGets.every(([url]) => !String(url).includes("limit="))).toBe(
      true,
    );
  });

  it("keeps the caught-up summary and hides Keep going when nothing remains due (REV-43)", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([clozeCard])),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, scheduling(later())),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Easy" }));

    expect(await screen.findByText("Session complete")).toBeTruthy();
    expect(screen.queryByTestId("done-for-today")).toBeNull();
    expect(screen.queryByRole("button", { name: "Keep going" })).toBeNull();
    expect(screen.queryByTestId("continue-reading")).toBeNull();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("/api/reading/continue"),
      ),
    ).toBe(false);
  });

  it("omits the book link when continue-reading is null rather than inventing one", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${DUE}`]: () =>
        jsonResponse(200, dueQueue([clozeCard], { total_due: 4 })),
      "POST /api/quiz-items/i1/reviews": () =>
        jsonResponse(200, scheduling(later())),
      "GET /api/reading/continue": () => jsonResponse(200, null),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    fireEvent.click(screen.getByRole("button", { name: "Good" }));

    expect(await screen.findByRole("button", { name: "Keep going" })).toBeTruthy();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) => String(url) === "/api/reading/continue",
        ),
      ).toBe(true),
    );
    expect(screen.queryByTestId("continue-reading")).toBeNull();
    expect(screen.queryByRole("link", { name: /continue reading/i })).toBeNull();
  });
});


describe("ReviewScreen in pt-BR", () => {
  /** Hold a response until the test releases it, to see the in-flight state. */
  function deferred() {
    let release: (response: Response) => void = () => {};
    const promise = new Promise<Response>((resolve) => {
      release = resolve;
    });
    return { promise, release };
  }

  const REVIEW_NAMESPACES = ["review", "errors.status", "common"];

  const body = () => document.body.textContent ?? "";

  it("loading, signed-out, empty and failed states: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    const auth = deferred();
    const due = deferred();
    let attempt = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => auth.promise,
        [`GET ${DUE}`]: () => {
          attempt += 1;
          return attempt === 1 ? due.promise : jsonResponse(200, dueQueue([]));
        },
      }),
    );
    render(<ReviewScreen />);

    expect(screen.getByText("Carregando…")).toBeTruthy();
    await act(async () => {
      auth.release(authedMe.clone());
    });
    expect(
      await screen.findByText("Carregando suas revisões pendentes…"),
    ).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    await act(async () => {
      due.release(jsonResponse(500, { detail: "Boom." }));
    });
    expect((await screen.findByRole("alert")).textContent).toBe(
      "O servidor teve um problema. Tente novamente.",
    );
    expect(screen.getByRole("region", { name: "revisão" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Nada para revisar agora.")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Voltar para a biblioteca" }),
    ).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    cleanup();

    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/auth/me": () => jsonResponse(401, {}) }),
    );
    render(<ReviewScreen />);
    expect(await screen.findByText("Você não está conectado.")).toBeTruthy();
  });

  it("card, grades, intervals and summary: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    const soon = new Date(Date.now() + 60 * 1000).toISOString();
    let firstReview = true;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(
            200,
            dueQueue([
              { ...clozeCard, interval_labels: { "1": "~1m", "2": "~10m", "3": "~1h", "4": "~1y" } },
              {
                ...recallCard,
                interval_labels: { "1": "~4d", "2": "~2w", "3": "~1mo", "4": "~4mo" },
              },
            ]),
          ),
        "POST /api/quiz-items/i1/reviews": () => {
          // The first grade comes due within minutes: a short-term requeue.
          const due = firstReview ? soon : "2026-08-20T00:00:00Z";
          firstReview = false;
          return jsonResponse(
            200,
            scheduling(due, {
              interval_labels: { "1": "~1d", "2": "~1d", "3": "~4d", "4": "~2w" },
            }),
          );
        },
        "POST /api/quiz-items/i2/reviews": () =>
          jsonResponse(200, scheduling("2026-08-20T00:00:00Z")),
      }),
    );
    render(<ReviewScreen />);

    await screen.findByTestId("question");
    expect(screen.getByText("lacuna")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Abrir no livro" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    expect(screen.getByRole("group", { name: "Avalie o quanto você lembrou" })).toBeTruthy();
    expect(
      [1, 2, 3, 4].map((r) => screen.getByTestId(`grade-interval-${r}`).textContent),
    ).toEqual(["~1 min", "~10 min", "~1 h", "~1 ano"]);
    for (const grade of ["Novamente", "Difícil", "Bom", "Fácil"]) {
      expect(screen.getByRole("button", { name: grade })).toBeTruthy();
    }
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);

    fireEvent.click(screen.getByRole("button", { name: "Novamente" }));
    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("2/3"),
    );
    expect(screen.getByTestId("short-term-remaining").textContent).toBe(
      "1 ainda em revisão de curto prazo",
    );
    expect(screen.getByText("resposta livre")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    expect(
      [1, 2, 3, 4].map((r) => screen.getByTestId(`grade-interval-${r}`).textContent),
    ).toEqual(["~4 dias", "~2 sem.", "~1 mês", "~4 meses"]);
    fireEvent.click(screen.getByRole("button", { name: "Bom" }));
    await waitFor(() =>
      expect(screen.getByTestId("position").textContent).toBe("3/3"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    // The requeued card carries the buckets its first grade returned.
    expect(screen.getByTestId("grade-interval-1").textContent).toBe("~1 dia");
    fireEvent.click(screen.getByRole("button", { name: "Fácil" }));

    expect(await screen.findByText("Sessão concluída")).toBeTruthy();
    expect(screen.getByTestId("reviewed-total").textContent).toBe(
      "3 cartões revisados.",
    );
    expect(screen.getByRole("region", { name: "resumo da revisão" })).toBeTruthy();
    expect(body()).toContain("Novamente:");
    expect(body()).toContain("Fácil:");
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
  });

  it("note badge, reset, edit and a failed grade: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    const reset = deferred();
    const save = deferred();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(
            200,
            dueQueue([
              {
                ...recallCard,
                provenance: { note_id: "n7", note_title: "Como a memória funciona" },
                note_changed: true,
              },
            ]),
          ),
        "POST /api/quiz-items/i2/schedule-reset": () => reset.promise,
        "PATCH /api/quiz-items/i2": () => save.promise,
        "POST /api/quiz-items/i2/reviews": () =>
          jsonResponse(500, { detail: "Boom." }),
      }),
    );
    render(<ReviewScreen />);
    await screen.findByTestId("question");

    expect(screen.getByTestId("note-changed-badge").textContent).toBe(
      "Sua nota mudou",
    );
    expect(screen.getByTestId("card-provenance").textContent).toBe(
      "Da nota “Como a memória funciona”",
    );
    fireEvent.click(screen.getByRole("button", { name: "Reiniciar agendamento" }));
    // The confirm dialog renders from an async state update; await it instead of
    // racing it with a synchronous body read.
    expect(await screen.findByRole("button", { name: "Cancelar" })).toBeTruthy();
    expect(body()).toContain("Reiniciar o agendamento deste cartão?");
    fireEvent.click(screen.getByRole("button", { name: "Confirmar reinício" }));
    expect(
      await screen.findByRole("button", { name: "Reiniciando…" }),
    ).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    await act(async () => {
      reset.release(
        jsonResponse(200, {
          state: 1,
          step: 0,
          stability: null,
          difficulty: null,
          due: "2026-07-20T00:00:00Z",
          last_review: null,
        }),
      );
    });

    act(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "e", bubbles: true, cancelable: true }),
      );
    });
    expect(await screen.findByLabelText("Pergunta")).toBeTruthy();
    expect(screen.getByLabelText("Resposta")).toBeTruthy();
    fireEvent.change(screen.getByTestId("edit-answer"), {
      target: { value: "Charles Babbage e Ada" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("button", { name: "Salvando…" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    await act(async () => {
      save.release(
        jsonResponse(200, {
          id: "i2",
          question: recallCard.question,
          answer: "Charles Babbage e Ada",
        }),
      );
    });

    await waitFor(() => expect(screen.queryByTestId("edit-question")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    fireEvent.click(screen.getByRole("button", { name: "Bom" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "O servidor teve um problema. Tente novamente.",
    );
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
  });

  it("unknown backend tokens show as sent: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(
            200,
            dueQueue([
              {
                ...clozeCard,
                item_type: "multiple_choice",
                interval_labels: { "1": "~3w", "2": "~10m", "3": "~4d", "4": "~2w" },
              },
            ]),
          ),
      }),
    );
    render(<ReviewScreen />);
    await screen.findByTestId("question");
    // A kind or bucket the catalog does not know yet stays visible, untranslated.
    expect(screen.getByText("multiple_choice")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    expect(screen.getByTestId("grade-interval-1").textContent).toBe("~3w");
    expect(screen.getByTestId("grade-interval-2").textContent).toBe("~10 min");
  });

  it("done for today: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () =>
          jsonResponse(200, dueQueue([clozeCard], { total_due: 3 })),
        "POST /api/quiz-items/i1/reviews": () =>
          jsonResponse(200, scheduling("2026-08-20T00:00:00Z")),
        "GET /api/reading/continue": () =>
          jsonResponse(200, {
            source_id: "s1",
            source_title: "Dom Casmurro",
            chapter_title: "Capítulo 1",
            percent: 42.5,
            updated_at: "2026-07-19T00:00:00Z",
          }),
      }),
    );
    render(<ReviewScreen />);
    await screen.findByTestId("question");
    fireEvent.click(screen.getByRole("button", { name: "Mostrar resposta" }));
    fireEvent.click(screen.getByRole("button", { name: "Bom" }));

    expect((await screen.findByTestId("done-for-today")).textContent).toBe(
      "Por hoje é só",
    );
    expect(body()).toContain("Você terminou esta sessão.");
    expect(screen.getByRole("button", { name: "Continuar revisando" })).toBeTruthy();
    expect((await screen.findByTestId("continue-reading")).textContent).toBe(
      "Continuar lendo Dom Casmurro",
    );
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
  });

  it("page title and loading fallback: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${DUE}`]: () => jsonResponse(200, dueQueue([])),
      }),
    );
    render(<ReviewPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Revisão" })).toBeTruthy();
    expect(await screen.findByText("Nada para revisar agora.")).toBeTruthy();
    expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    cleanup();

    // While the search params are not ready the page shows its own fallback.
    nav.suspend = true;
    try {
      render(<ReviewPage />);
      expect(await screen.findByText("Carregando…")).toBeTruthy();
      expectNoEnglishCopy(body(), ...REVIEW_NAMESPACES);
    } finally {
      nav.suspend = false;
    }
  });

  it("heatmap uses locale names", async () => {
    setTestLocale("pt-BR");
    const today = new Date(2026, 6, 20); // 2026-07-20 local, a Monday
    const days = [
      { day: "2026-07-20", reviews_count: 7, reading_updates: 2, pages: 9 },
      { day: "2026-07-14", reviews_count: 1, reading_updates: 0, pages: 1 },
      // Read but not reviewed: zero reads as a plural in Portuguese.
      { day: "2026-07-13", reviews_count: 0, reading_updates: 2, pages: 0 },
    ];
    const { container } = render(<StudyHeatmap days={days} today={today} />);

    const weekdays = container.querySelector('[data-testid="heatmap-weekdays"]')!;
    expect([...weekdays.children].map((row) => row.textContent)).toEqual([
      "",
      "seg.",
      "",
      "qua.",
      "",
      "sex.",
      "",
    ]);
    const months = container.querySelector('[data-testid="heatmap-months"]')!;
    expect([...months.children].map((m) => m.textContent)).toEqual([
      "abr.",
      "mai.",
      "jun.",
      "jul.",
    ]);
    expect(
      screen.getByRole("group", {
        name: "mapa de atividade de estudo, últimas 12 semanas",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "seg., 20 de jul.: 7 revisões · 9 páginas" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "ter., 14 de jul.: 1 revisão · 1 página" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "seg., 13 de jul.: 0 revisões · 0 páginas" }),
    ).toBeTruthy();
    fireEvent.mouseEnter(container.querySelector('[data-day="2026-07-20"]')!);
    expect(screen.getByTestId("tooltip-day").textContent).toBe("seg., 20 de jul.");
    expect(container.textContent).toContain("Últimas 12 semanas");
    expect(screen.getByTestId("heatmap-legend").textContent).toBe("MenosMais");
    expectNoEnglishCopy(container.textContent ?? "", "review.heatmap");
    cleanup();

    // The stats card around it: title, toggle, streak line and totals.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, {
          days: [
            { day: "2026-07-20", reviews_count: 1234, reading_updates: 0, pages: 3 },
          ],
          studied_last_14: 9,
        }),
      ),
    );
    render(<StudyStats />);
    expect((await screen.findByTestId("streak-line")).textContent).toBe(
      "Você estudou em 9 dos últimos 14 dias",
    );
    expect(screen.getByRole("button", { name: "Ocultar estatísticas" })).toBeTruthy();
    expect(screen.getByLabelText("estatísticas de estudo")).toBeTruthy();
    expect(screen.getByTestId("study-totals").textContent).toBe("1.234revisões3páginas");
    expectNoEnglishCopy(document.body.textContent ?? "", "review.stats", "review.heatmap");
    fireEvent.click(screen.getByRole("button", { name: "Ocultar estatísticas" }));
    expect(screen.getByRole("button", { name: "Mostrar estatísticas" })).toBeTruthy();
    expect(screen.queryByTestId("study-heatmap")).toBeNull();
    expectNoEnglishCopy(document.body.textContent ?? "", "review.stats");
    localStorage.clear();
  });
});
