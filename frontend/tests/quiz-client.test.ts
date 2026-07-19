/**
 * E1 gate (logic) — quiz + review client calls the same-origin proxy (QUIZ-21).
 *
 * Verifies each helper targets the right same-origin path with `credentials:
 * "same-origin"`, echoes the CSRF token in `X-CSRF-Token` on the state-changing
 * generate-deck/submit-review calls (AD-007) and sends none on the two reads,
 * builds the due-queue query from the optional `source_id`/`limit`, passes each
 * success payload (job, overview, due queue with citation fields + answer,
 * scheduling snapshot) through unchanged, and surfaces the backend `detail` —
 * with a readable fallback for a 422 list detail or an unparseable body — on
 * every documented error status (401/404/409/422/429/502). `quizExportUrl` is a
 * pure same-origin URL builder (no fetch). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  generateDeck,
  getDueReviews,
  getQuizOverview,
  quizExportUrl,
  submitReview,
  type DueItem,
  type DueQueue,
  type QuizJob,
  type QuizOverview,
  type Scheduling,
} from "../app/lib/quiz";

const job: QuizJob = {
  id: "job1",
  status: "queued",
  attempts: 0,
  generated_count: 0,
  discarded_count: 0,
  failed_sections: 0,
  error: null,
  created_at: "now",
  updated_at: "now",
};

const overview: QuizOverview = {
  items: [
    {
      id: "i1",
      item_type: "cloze",
      question: "Ada wrote the first ____.",
      status: "active",
      due: "2026-07-16T00:00:00Z",
    },
    {
      id: "i2",
      item_type: "free_recall",
      question: "Who wrote the first algorithm?",
      status: "stale",
      due: null,
    },
  ],
  counts_by_status: { active: 1, stale: 1 },
  due_count: 1,
  latest_job: { ...job, status: "succeeded", generated_count: 2 },
};

const dueItem: DueItem = {
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

const dueQueue: DueQueue = { items: [dueItem], total_due: 12 };

const scheduling: Scheduling = {
  state: 2,
  step: null,
  stability: 4.2,
  difficulty: 5.1,
  due: "2026-07-20T00:00:00Z",
  last_review: "2026-07-16T00:00:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fetchMockFn(
  impl: (...args: [string, RequestInit]) => Promise<Response>,
) {
  return vi.fn<(...args: [string, RequestInit]) => Promise<Response>>(impl);
}

describe("getQuizOverview (E1)", () => {
  it("GETs the per-source quiz path (no CSRF) and passes the overview through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, overview));

    const result = await getQuizOverview(
      "s1",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(overview);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/quiz");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();

    // The fields the library reads survive the round-trip.
    expect(result.due_count).toBe(1);
    expect(result.counts_by_status).toEqual({ active: 1, stale: 1 });
    expect(result.latest_job?.status).toBe("succeeded");
    expect(result.items[1].status).toBe("stale");
  });

  it("surfaces the backend detail on a 404 missing/non-owned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Source not found." }),
    );

    await expect(
      getQuizOverview("s1", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Source not found.");
  });
});

describe("generateDeck (E1)", () => {
  it("POSTs the deck path with the CSRF token and passes the queued job through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(202, job));

    const result = await generateDeck(
      "s1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(job);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/quiz/deck");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(result.status).toBe("queued");
  });

  it("surfaces the backend detail on a 409 already-running response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "Deck generation already running." }),
    );

    await expect(
      generateDeck("s1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Deck generation already running.");
  });

  it("surfaces the backend detail on a 429 rate-limited response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(429, { detail: "Too many requests. Try again shortly." }),
    );

    await expect(
      generateDeck("s1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Too many requests. Try again shortly.");
  });

  it("surfaces the backend detail on a 502 enqueue-failure response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(502, { detail: "Could not start quiz deck generation." }),
    );

    await expect(
      generateDeck("s1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Could not start quiz deck generation.");
  });
});

describe("getDueReviews (E1)", () => {
  it("GETs the due path with no query when no filters are given (no CSRF)", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, dueQueue));

    const result = await getDueReviews({}, fetchMock as unknown as typeof fetch);

    expect(result).toEqual(dueQueue);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/reviews/due");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();

    // The card fields the review screen renders survive the round-trip.
    expect(result.total_due).toBe(12);
    expect(result.items[0].answer).toBe("algorithm");
    expect(result.items[0].citation.section_path).toEqual([
      "Chapter 1",
      "Core Idea",
    ]);
    expect(result.items[0].citation.source_excerpt).toBe(
      "Ada wrote the first algorithm.",
    );
    expect(result.items[0].citation.anchor).toBe("chapter-1.xhtml#core-idea");
  });

  it("builds the query from the source_id and limit filters", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, dueQueue));

    await getDueReviews(
      { sourceId: "s1", limit: 50 },
      fetchMock as unknown as typeof fetch,
    );

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/reviews/due?source_id=s1&limit=50");
  });

  it("defaults to no filters when called with no argument", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, dueQueue));

    await getDueReviews(undefined, fetchMock as unknown as typeof fetch);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/reviews/due");
  });

  it("surfaces the backend detail on a 401 unauthenticated response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    await expect(
      getDueReviews({}, fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Not authenticated.");
  });
});

describe("submitReview (E1)", () => {
  it("POSTs {rating, review_duration_ms} with the CSRF token and passes scheduling through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, scheduling));

    const result = await submitReview(
      "i1",
      { rating: 3, review_duration_ms: 4200 },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(scheduling);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/quiz-items/i1/reviews");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      rating: 3,
      review_duration_ms: 4200,
    });

    // The advanced schedule the screen surfaces survives the round-trip.
    expect(result.due).toBe("2026-07-20T00:00:00Z");
    expect(result.state).toBe(2);
  });

  it("omits review_duration_ms from the body when it is not supplied", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, scheduling));

    await submitReview(
      "i1",
      { rating: 1 },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      rating: 1,
    });
  });

  it("surfaces the backend detail on a 409 stale/orphaned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "Item suspended after re-ingest." }),
    );

    await expect(
      submitReview(
        "i1",
        { rating: 3 },
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Item suspended after re-ingest.");
  });

  it("falls back to a readable message when a 422 detail is a list, not a string", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, {
        detail: [
          { type: "greater_than_equal", loc: ["body", "rating"], msg: "ge 1" },
        ],
      }),
    );

    await expect(
      submitReview(
        "i1",
        { rating: 0 },
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Could not submit your review.");
  });

  it("falls back to a readable message when the error body is not parseable", async () => {
    const fetchMock = fetchMockFn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    );

    await expect(
      submitReview(
        "i1",
        { rating: 3 },
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Could not submit your review.");
  });
});

describe("quizExportUrl (E1)", () => {
  it("builds the same-origin export URL for a source (no fetch)", () => {
    expect(quizExportUrl("s1")).toBe("/api/sources/s1/quiz/export");
  });
});
