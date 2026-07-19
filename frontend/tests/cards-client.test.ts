/**
 * D1 gate (logic) — the cards client calls the same-origin proxy.
 *
 * Verifies each helper targets the right same-origin path with `credentials:
 * "same-origin"`, echoes the CSRF token in `X-CSRF-Token` on all three
 * state-changing calls (AD-007), passes each success payload through unchanged,
 * and surfaces a typed `CardError` on every documented error status. The 409
 * mapping is per-route by design: a stale passage on the capture routes
 * (`stale_capture`, CAP-08) versus a deck card that cannot be reworded on the edit
 * route (`not_editable`), so a caller can branch without inspecting the URL. Two
 * outcomes the flow depends on are pinned as *successes*, not errors: an empty
 * suggestion list (CAP-01, "no cards for this passage") and a 200 idempotent
 * re-accept (CAP-05, the double-submit edge case). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  acceptCard,
  CardError,
  suggestCards,
  updateCard,
  type Card,
  type CardSuggestion,
} from "../app/lib/cards";

const suggestion: CardSuggestion = {
  item_type: "free_recall",
  question: "Who wrote the first algorithm?",
  answer: "Ada Lovelace",
  anchor_quote: "Ada Lovelace wrote the first algorithm",
};

const card: Card = {
  id: "c1",
  source_id: "s1",
  origin: "highlight",
  note_anchor_id: "a1",
  item_type: "free_recall",
  question: "Who wrote the first algorithm?",
  answer: "Ada Lovelace",
  citation: {
    section_path: ["Chapter 1", "Core Idea"],
    anchor: "chapter-1.xhtml#core-idea",
    source_excerpt: "Ada Lovelace wrote the first algorithm",
  },
  status: "active",
  created_at: "now",
  updated_at: "now",
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

describe("suggestCards (CAP-01)", () => {
  it("POSTs the suggestions path with the CSRF token and the highlight id", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(200, { suggestions: [suggestion] }),
    );

    const result = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual([suggestion]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/cards/suggestions");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ note_anchor_id: "a1" });
    // The grounding quote the chip shows survives the round-trip.
    expect(result[0].anchor_quote).toBe(
      "Ada Lovelace wrote the first algorithm",
    );
  });

  it("returns an empty list rather than an error when no candidate survives QC", async () => {
    // "No cards for this passage" is a normal 200 outcome, not a failure — the
    // caller must be able to tell it apart from a generation error.
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(200, { suggestions: [] }),
    );

    const result = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual([]);
  });

  it("raises a stale_capture CardError on a 409 changed-passage response (CAP-08)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "The book changed while you were reading." }),
    );

    const err = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("stale_capture");
    expect(err.status).toBe(409);
    expect(err.message).toBe("The book changed while you were reading.");
  });

  it("raises an unknown CardError on a 404 missing/non-owned highlight", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Not found." }),
    );

    const err = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(404);
  });

  it("raises an unknown CardError on a 429 throttled response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(429, { detail: "Too many requests." }),
    );

    const err = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(429);
    expect(err.message).toBe("Too many requests.");
  });

  it("falls back to a readable message when the error body is not parseable", async () => {
    const fetchMock = fetchMockFn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    );

    const err = await suggestCards(
      "s1",
      "a1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("unknown");
    expect(err.message).toBe("Could not suggest cards for this passage.");
  });
});

describe("acceptCard (CAP-05)", () => {
  it("POSTs the cards path with the CSRF token and the accepted text", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, card));

    const body = {
      note_anchor_id: "a1",
      item_type: "free_recall",
      question: "Who wrote the first algorithm?",
      answer: "Ada Lovelace",
    };
    const result = await acceptCard(
      "s1",
      body,
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(card);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/cards");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual(body);
    // The provenance back to the highlight rides along for the caller.
    expect(result.note_anchor_id).toBe("a1");
    expect(result.origin).toBe("highlight");
  });

  it("treats a 200 idempotent re-accept as success, returning the existing card", async () => {
    // A double submit answers 200 with the card that already exists; the client
    // must surface it as the same success as a 201, never as an error.
    const fetchMock = fetchMockFn(async () => jsonResponse(200, card));

    const result = await acceptCard(
      "s1",
      {
        note_anchor_id: "a1",
        item_type: "free_recall",
        question: "Who wrote the first algorithm?",
        answer: "Ada Lovelace",
      },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(card);
    expect(result.id).toBe("c1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("raises an invalid CardError on a 422 empty or over-long text response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Card text cannot be empty." }),
    );

    const err = await acceptCard(
      "s1",
      { note_anchor_id: "a1", item_type: "free_recall", question: "", answer: "x" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("invalid");
    expect(err.status).toBe(422);
    expect(err.message).toBe("Card text cannot be empty.");
  });

  it("falls back to a readable message when a 422 detail is a list, not a string", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, {
        detail: [{ type: "string_type", loc: ["body", "question"], msg: "str" }],
      }),
    );

    const err = await acceptCard(
      "s1",
      { note_anchor_id: "a1", item_type: "free_recall", question: "q", answer: "a" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("invalid");
    expect(err.message).toBe("Could not save this card.");
  });
});

describe("updateCard (CAP-12)", () => {
  it("PATCHes the quiz-item path with the CSRF token and the new text", async () => {
    const reworded = { ...card, question: "Who wrote the very first algorithm?" };
    const fetchMock = fetchMockFn(async () => jsonResponse(200, reworded));

    const result = await updateCard(
      "c1",
      { question: "Who wrote the very first algorithm?", answer: "Ada Lovelace" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(reworded);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/quiz-items/c1");
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual({
      question: "Who wrote the very first algorithm?",
      answer: "Ada Lovelace",
    });
    // The identity is unchanged by a reword — the whole point of CAP-12.
    expect(result.id).toBe("c1");
  });

  it("maps the edit route's 409 to not_editable, not to a stale passage", async () => {
    // The same status means something different here than on the capture routes:
    // this card is deck-origin, so its text is not the student's to rewrite.
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "This card cannot be edited." }),
    );

    const err = await updateCard(
      "c1",
      { question: "q", answer: "a" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("not_editable");
    expect(err.status).toBe(409);
    expect(err.message).toBe("This card cannot be edited.");
  });

  it("raises an invalid CardError on a 422 empty or over-long text response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Card text is too long." }),
    );

    const err = await updateCard(
      "c1",
      { question: "q", answer: "a" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("invalid");
    expect(err.message).toBe("Card text is too long.");
  });
});
