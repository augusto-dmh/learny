/**
 * D1 gate (unit) — the streaming transport reshapes each request to Learny's
 * contract (latest user message only → `{question}` / `{message}`, CSRF header,
 * the stream URL) exactly as FE-06/FE-12 require; persisted teaching turns map to
 * seeded `useChat` messages that carry the same citation + answer-status parts a
 * live stream assembles (FE-12); and every pre-stream failure maps to a readable
 * message (FE-09/FE-13).
 */

import type { PrepareSendMessagesRequest } from "ai";
import { describe, expect, it } from "vitest";

import { type Citation } from "../app/lib/questions";
import {
  createQuestionTransport,
  createTurnTransport,
  errorMessageFor,
  turnsToUIMessages,
  type LearnyUIMessage,
} from "../app/lib/streaming";
import { type TeachingTurnView } from "../app/lib/teaching";

type Prepared = {
  api?: string;
  body: Record<string, unknown>;
  headers?: Record<string, string>;
};

/** Reach the transport's `prepareSendMessagesRequest` (a protected instance field). */
function prepareOf(
  transport: unknown,
): PrepareSendMessagesRequest<LearnyUIMessage> {
  return (
    transport as {
      prepareSendMessagesRequest: PrepareSendMessagesRequest<LearnyUIMessage>;
    }
  ).prepareSendMessagesRequest;
}

/** Invoke the prepare hook with a full options object; `api: "IGNORED"` proves the
 * transport supplies its own URL rather than echoing the caller's. */
async function callPrepare(
  transport: unknown,
  messages: LearnyUIMessage[],
): Promise<Prepared> {
  const prepare = prepareOf(transport);
  return (await prepare({
    id: "chat-1",
    messages,
    requestMetadata: undefined,
    body: undefined,
    credentials: undefined,
    headers: undefined,
    api: "IGNORED",
    trigger: "submit-message",
    messageId: undefined,
  })) as Prepared;
}

function userMessage(id: string, text: string): LearnyUIMessage {
  return { id, role: "user", parts: [{ type: "text", text }] };
}

function assistantText(id: string, text: string): LearnyUIMessage {
  return { id, role: "assistant", parts: [{ type: "text", text }] };
}

const citation: Citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: "chapter-1.xhtml#core-idea",
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

describe("createQuestionTransport request shaping (D1)", () => {
  it("POSTs the latest user text as {question} to the source stream URL with the CSRF header", async () => {
    const transport = createQuestionTransport("s1", "csrf-xyz");
    const prepared = await callPrepare(transport, [
      userMessage("m0", "an earlier question"),
      assistantText("a0", "an earlier answer"),
      userMessage("m1", "Who wrote the first algorithm?"),
    ]);

    expect(prepared.api).toBe("/api/sources/s1/questions/stream");
    expect(prepared.body).toEqual({ question: "Who wrote the first algorithm?" });
    expect(prepared.headers).toEqual({ "X-CSRF-Token": "csrf-xyz" });
  });
});

describe("createTurnTransport request shaping (D1)", () => {
  it("POSTs the latest user text as {message} to the session turns stream URL with the CSRF header", async () => {
    const transport = createTurnTransport("sess1", "csrf-abc");
    const prepared = await callPrepare(transport, [
      userMessage("m1", "Explain this chapter."),
    ]);

    expect(prepared.api).toBe("/api/teaching-sessions/sess1/turns/stream");
    expect(prepared.body).toEqual({ message: "Explain this chapter." });
    expect(prepared.headers).toEqual({ "X-CSRF-Token": "csrf-abc" });
  });
});

describe("turnsToUIMessages (D1)", () => {
  const answered: TeachingTurnView = {
    turn_index: 0,
    message: "What is this about?",
    answer_status: "answered",
    text: "It is about early computing.",
    citations: [citation],
    evidence_count: 8,
    model: "local-extractive",
    created_at: "now",
  };
  const notFound: TeachingTurnView = {
    turn_index: 1,
    message: "and the weather?",
    answer_status: "not_found_in_source",
    text: "",
    citations: [],
    evidence_count: 0,
    model: "local-extractive",
    created_at: "now",
  };

  it("maps each turn to a user message and an assistant message carrying text, citations, and status parts", () => {
    const messages = turnsToUIMessages([answered, notFound]);

    // Two messages per turn, in order.
    expect(messages.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ]);

    // The answered turn's user prompt and assistant text.
    expect(messages[0].parts).toEqual([
      { type: "text", text: "What is this about?" },
    ]);
    const answeredParts = messages[1].parts;
    expect(answeredParts).toContainEqual({
      type: "text",
      text: "It is about early computing.",
    });
    // The citation snapshot rides on a data-citations part, verbatim.
    expect(answeredParts).toContainEqual({
      type: "data-citations",
      data: [citation],
    });
    // The answer status rides on a data-answer-status part.
    expect(answeredParts).toContainEqual({
      type: "data-answer-status",
      data: { status: "answered" },
    });

    // The not-found turn seeds an empty citation list and its status.
    const notFoundParts = messages[3].parts;
    expect(notFoundParts).toContainEqual({ type: "data-citations", data: [] });
    expect(notFoundParts).toContainEqual({
      type: "data-answer-status",
      data: { status: "not_found_in_source" },
    });
  });
});

describe("errorMessageFor (D1)", () => {
  it("maps each pre-stream failure to a distinct readable message", () => {
    expect(errorMessageFor(401)).toMatch(/sign in/i);
    expect(errorMessageFor(403)).toMatch(/verif/i);
    expect(errorMessageFor(404)).toMatch(/could not be found/i);
    expect(errorMessageFor(409)).toMatch(/still processing/i);
    expect(errorMessageFor(422)).toMatch(/could not be processed/i);
    expect(errorMessageFor(429)).toMatch(/too many requests/i);
    expect(errorMessageFor(502)).toMatch(/generation failed/i);
    expect(errorMessageFor("network")).toMatch(/reaching the server/i);
    // An unmapped status still yields a readable fallback.
    expect(errorMessageFor(500)).toMatch(/something went wrong/i);
  });
});
