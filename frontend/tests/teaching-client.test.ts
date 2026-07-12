/**
 * E1 gate (logic) — teaching-sessions client calls the same-origin proxy
 * (TEACH-22).
 *
 * Verifies each helper targets the right same-origin path with `credentials:
 * "same-origin"`, echoes the CSRF token in `X-CSRF-Token` on the state-changing
 * start/turn calls (AD-007) and sends none on the two reads, passes each success
 * payload through unchanged (answered + not-found turns, ordered history,
 * summary list), and surfaces the backend `detail` — with a readable fallback
 * for a 422 list detail or an unparseable body — on every documented error
 * status (404/409/422/429/502). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  getTeachingSession,
  listTeachingSessions,
  postTeachingTurn,
  startTeachingSession,
  type TeachingSessionDetail,
  type TeachingSessionSummary,
  type TeachingSessionView,
  type TeachingTurnView,
} from "../app/lib/teaching";

const target = {
  anchor: "chapter-1.xhtml",
  section_path: ["Chapter 1"],
  title: "Chapter 1",
};

const session: TeachingSessionView = {
  id: "sess1",
  source_id: "s1",
  target,
  created_at: "now",
};

const answeredTurn: TeachingTurnView = {
  turn_index: 0,
  message: "Who wrote the first algorithm?",
  answer_status: "answered",
  text: "Ada Lovelace wrote the first algorithm.",
  citations: [
    {
      chunk_id: "c1",
      source_id: "s1",
      section_path: ["Chapter 1", "Core Idea"],
      anchor: "chapter-1.xhtml#core-idea",
      page_span: null,
      snippet: "the first algorithm",
      score: 0.03,
    },
  ],
  evidence_count: 8,
  model: "local-extractive",
  created_at: "now",
};

const notFoundTurn: TeachingTurnView = {
  turn_index: 1,
  message: "nonsense",
  answer_status: "not_found_in_source",
  text: "",
  citations: [],
  evidence_count: 0,
  model: "local-extractive",
  created_at: "later",
};

const detail: TeachingSessionDetail = {
  ...session,
  turns: [answeredTurn, notFoundTurn],
};

const summaries: TeachingSessionSummary[] = [
  { id: "sess2", target, created_at: "later", turn_count: 3 },
  { id: "sess1", target, created_at: "earlier", turn_count: 1 },
];

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

describe("startTeachingSession (E1)", () => {
  it("POSTs {source_id, target_anchor} to the same-origin path with the CSRF token", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, session));

    const result = await startTeachingSession(
      "s1",
      "chapter-1.xhtml",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(session);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/teaching-sessions");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      source_id: "s1",
      target_anchor: "chapter-1.xhtml",
    });
  });

  it("surfaces the backend detail on a 404 not-found response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Source not found." }),
    );

    await expect(
      startTeachingSession(
        "s1",
        "a",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Source not found.");
  });

  it("surfaces the backend detail on a 409 not-ready response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "Source is not ready." }),
    );

    await expect(
      startTeachingSession(
        "s1",
        "a",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Source is not ready.");
  });

  it("surfaces the backend detail on a 422 unknown-target response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Unknown teaching target." }),
    );

    await expect(
      startTeachingSession(
        "s1",
        "ghost",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Unknown teaching target.");
  });

  it("surfaces the backend detail on a 429 rate-limited response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(429, { detail: "Too many requests. Try again shortly." }),
    );

    await expect(
      startTeachingSession(
        "s1",
        "a",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Too many requests. Try again shortly.");
  });
});

describe("getTeachingSession (E1)", () => {
  it("GETs the session path (no CSRF) and passes the ordered cited history through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, detail));

    const result = await getTeachingSession(
      "sess1",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(detail);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/teaching-sessions/sess1");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();

    // History order and per-turn citation fields survive the round-trip.
    expect(result.turns.map((t) => t.turn_index)).toEqual([0, 1]);
    expect(result.turns[0].text).toBe("Ada Lovelace wrote the first algorithm.");
    expect(result.turns[0].citations[0].section_path).toEqual([
      "Chapter 1",
      "Core Idea",
    ]);
    expect(result.turns[1].answer_status).toBe("not_found_in_source");
    expect(result.turns[1].citations).toEqual([]);
  });

  it("surfaces the backend detail on a 404 missing/non-owned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Session not found." }),
    );

    await expect(
      getTeachingSession("sess1", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Session not found.");
  });
});

describe("listTeachingSessions (E1)", () => {
  it("GETs the per-source path (no CSRF) and passes the newest-first summaries through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, summaries));

    const result = await listTeachingSessions(
      "s1",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(summaries);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/teaching-sessions");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
    expect(result.map((s) => s.id)).toEqual(["sess2", "sess1"]);
    expect(result[0].turn_count).toBe(3);
  });

  it("returns an empty list when the source has no sessions", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, []));

    const result = await listTeachingSessions(
      "s1",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual([]);
  });

  it("surfaces the backend detail on a 404 missing/non-owned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Source not found." }),
    );

    await expect(
      listTeachingSessions("s1", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Source not found.");
  });
});

describe("postTeachingTurn (E1)", () => {
  it("POSTs {message} to the turns path with the CSRF token and passes the answered turn through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, answeredTurn));

    const result = await postTeachingTurn(
      "sess1",
      "Who wrote the first algorithm?",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(answeredTurn);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/teaching-sessions/sess1/turns");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      message: "Who wrote the first algorithm?",
    });

    // The cited fields the panel renders survive the round-trip.
    expect(result.answer_status).toBe("answered");
    expect(result.text).toBe("Ada Lovelace wrote the first algorithm.");
    expect(result.model).toBe("local-extractive");
    expect(result.citations[0].snippet).toBe("the first algorithm");
  });

  it("passes the not-found turn through with empty text and citations", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, notFoundTurn));

    const result = await postTeachingTurn(
      "sess1",
      "nonsense",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result.answer_status).toBe("not_found_in_source");
    expect(result.text).toBe("");
    expect(result.citations).toEqual([]);
  });

  it("surfaces the backend detail on a 409 target-gone response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, {
        detail: "Target no longer exists; start a new session.",
      }),
    );

    await expect(
      postTeachingTurn(
        "sess1",
        "q",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Target no longer exists; start a new session.");
  });

  it("surfaces the backend detail on a 429 rate-limited response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(429, { detail: "Too many requests. Try again shortly." }),
    );

    await expect(
      postTeachingTurn(
        "sess1",
        "q",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Too many requests. Try again shortly.");
  });

  it("surfaces the backend detail on a 502 generation-failed response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(502, { detail: "Generation failed. Please try again." }),
    );

    await expect(
      postTeachingTurn(
        "sess1",
        "q",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Generation failed. Please try again.");
  });

  it("falls back to a readable message when a 422 detail is a list, not a string", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, {
        detail: [
          { type: "string_too_long", loc: ["body", "message"], msg: "too long" },
        ],
      }),
    );

    await expect(
      postTeachingTurn(
        "sess1",
        "q",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Could not send your message.");
  });

  it("falls back to a readable message when the error body is not parseable", async () => {
    const fetchMock = fetchMockFn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    );

    await expect(
      postTeachingTurn(
        "sess1",
        "q",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Could not send your message.");
  });
});
