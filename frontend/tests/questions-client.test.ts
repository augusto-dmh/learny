/**
 * D1 gate (logic) — questions client calls the same-origin proxy (QA-21/QA-20).
 *
 * Verifies askQuestion POSTs `{question}` as JSON to
 * `/api/sources/{id}/questions` (never cross-origin) with `credentials:
 * "same-origin"` and the CSRF token echoed in `X-CSRF-Token` (AD-007, mirroring
 * sources.ts), that both 200 outcomes (answered / not-found) pass through
 * unchanged, and that a non-OK response surfaces the backend `detail` with a
 * readable fallback. No real network.
 */

import { describe, expect, it, vi } from "vitest";

import { askQuestion, type AnswerView } from "../app/lib/questions";

const answered: AnswerView = {
  answer_status: "answered",
  answer: "Ada Lovelace wrote the first algorithm.",
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
  retrieval: { strategy: "hybrid", evidence_count: 8 },
  model: "local-extractive",
};

const notFound: AnswerView = {
  answer_status: "not_found_in_source",
  answer: "",
  citations: [],
  retrieval: { strategy: "hybrid", evidence_count: 0 },
  model: "local-extractive",
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

describe("questions client (D1)", () => {
  it("POSTs {question} as JSON to the same-origin questions path with the CSRF token", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, answered));

    const result = await askQuestion(
      "s1",
      "Who wrote the first algorithm?",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(answered);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/questions");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      question: "Who wrote the first algorithm?",
    });
  });

  it("passes the answered payload through, preserving each citation's fields", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, answered));

    const result = await askQuestion(
      "s1",
      "q",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result.answer_status).toBe("answered");
    expect(result.answer).toBe("Ada Lovelace wrote the first algorithm.");
    expect(result.model).toBe("local-extractive");
    expect(result.retrieval).toEqual({ strategy: "hybrid", evidence_count: 8 });
    expect(result.citations[0].section_path).toEqual([
      "Chapter 1",
      "Core Idea",
    ]);
    expect(result.citations[0].snippet).toBe("the first algorithm");
  });

  it("passes the not-found payload through with empty citations", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, notFound));

    const result = await askQuestion(
      "s1",
      "nonsense",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result.answer_status).toBe("not_found_in_source");
    expect(result.answer).toBe("");
    expect(result.citations).toEqual([]);
  });

  it("surfaces the backend detail on a 409 not-ready response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "Source is not ready for questions." }),
    );

    await expect(
      askQuestion("s1", "q", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Source is not ready for questions.");
  });

  it("surfaces the backend detail on a 429 rate-limited response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(429, { detail: "Too many questions. Try again shortly." }),
    );

    await expect(
      askQuestion("s1", "q", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Too many questions. Try again shortly.");
  });

  it("surfaces the backend detail on a 502 generation-failed response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(502, { detail: "Answer generation failed. Please try again." }),
    );

    await expect(
      askQuestion("s1", "q", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Answer generation failed. Please try again.");
  });

  it("falls back to a readable message when a 422 detail is a list, not a string", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, {
        detail: [{ type: "string_too_long", loc: ["body", "question"], msg: "too long" }],
      }),
    );

    await expect(
      askQuestion("s1", "q", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Could not get an answer.");
  });

  it("falls back to a readable message when the error body is not parseable", async () => {
    const fetchMock = fetchMockFn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    );

    await expect(
      askQuestion("s1", "q", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Could not get an answer.");
  });
});
