/**
 * D1 gate (logic) — the cards client calls the same-origin proxy.
 *
 * Verifies each helper targets the right same-origin path with `credentials:
 * "same-origin"`, echoes the CSRF token in `X-CSRF-Token` on both state-changing
 * calls (AD-007), passes each success payload through unchanged, and surfaces a
 * typed `CardError` on every documented error status — 409 as `stale_capture`
 * (CAP-08, the passage moved under the highlight) and 422 as `invalid`. Two
 * outcomes the flow depends on are pinned as *successes*, not errors: an empty
 * suggestion list (CAP-01, "no cards for this passage") and a 200 idempotent
 * re-accept (CAP-05, the double-submit edge case). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  acceptCard,
  acceptNoteCard,
  CardError,
  suggestCards,
  suggestNoteCards,
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

describe("suggestNoteCards (NL-08)", () => {
  it("POSTs the note suggest path with the CSRF token and no highlight", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(200, { suggestions: [suggestion] }),
    );

    const result = await suggestNoteCards(
      "n1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual([suggestion]);
    const [url, init] = fetchMock.mock.calls[0];
    // The note is the whole source — addressed in the path, no anchor body.
    expect(url).toBe("/api/notes/n1/cards/suggest");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("returns an empty list rather than an error when QC grounds nothing", async () => {
    // "No cards could be grounded" is a normal 200 outcome, not a failure.
    const fetchMock = fetchMockFn(async () => jsonResponse(200, { suggestions: [] }));

    const result = await suggestNoteCards(
      "n1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual([]);
  });

  it("surfaces a readable, retryable error on a 502 provider failure", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(502, { detail: "The card generator is unavailable." }),
    );

    const err = await suggestNoteCards(
      "n1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(502);
    expect(err.message).toBe("The card generator is unavailable.");
  });
});

describe("acceptNoteCard (NL-09/NL-15)", () => {
  const noteCard: Card = {
    ...card,
    id: "nc1",
    source_id: null,
    origin: "note",
    note_anchor_id: null,
  };

  it("POSTs the note cards path and reports a fresh promote as created", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, noteCard));

    const body = {
      item_type: "free_recall",
      question: "What schedules reviews?",
      answer: "Spaced repetition",
    };
    const result = await acceptNoteCard(
      "n1",
      body,
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result.card).toEqual(noteCard);
    expect(result.created).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes/n1/cards");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it("reports an idempotent re-promote (200) as not created, returning the existing card", async () => {
    // NL-15: promoting the same text twice returns the existing card with 200 — the
    // caller must be able to tell this apart from a fresh 201 so its count stays honest.
    const fetchMock = fetchMockFn(async () => jsonResponse(200, noteCard));

    const result = await acceptNoteCard(
      "n1",
      { item_type: "free_recall", question: "q", answer: "a" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result.card.id).toBe("nc1");
    expect(result.created).toBe(false);
  });

  it("raises an invalid CardError on a 422 empty or over-long text response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Card text cannot be empty." }),
    );

    const err = await acceptNoteCard(
      "n1",
      { item_type: "free_recall", question: "", answer: "x" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(CardError);
    expect(err.kind).toBe("invalid");
    expect(err.status).toBe(422);
    expect(err.message).toBe("Card text cannot be empty.");
  });
});
