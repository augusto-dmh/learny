/**
 * The conversations client is the browser's whole view of the unified surface.
 * It carries the explicit notes choice and the requested scope into a start,
 * narrows the list to one book, and echoes the CSRF token on every mutating
 * call. Its failures are typed so a caller can tell a conversation that is gone
 * from one that could not be reached, and a start failure carries the status the
 * streaming surface already knows how to render.
 */

import { describe, expect, it, vi } from "vitest";

import {
  ConversationRequestError,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  startConversation,
} from "../app/lib/conversations";
import { StreamRequestError } from "../app/lib/streaming";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const conversation = {
  id: "conv1",
  source_id: "s1",
  title: "Untitled conversation",
  scope_anchors: [],
  include_notes: true,
  created_at: "now",
  updated_at: "now",
};

describe("startConversation", () => {
  it("sends the source, the requested scope, and the notes choice with the CSRF token", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, conversation));
    const started = await startConversation(
      {
        sourceId: "s1",
        scopeAnchors: ["c2.xhtml"],
        includeNotes: false,
        title: "Chapter 2",
      },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(started.id).toBe("conv1");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/conversations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      source_id: "s1",
      scope_anchors: ["c2.xhtml"],
      include_notes: false,
      title: "Chapter 2",
    });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("sends the whole-book scope and the notes choice even when the choice is the default", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, conversation));
    await startConversation(
      { sourceId: "s1", includeNotes: true },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    // The flag is never omitted: the server has no default to fall back on.
    expect(JSON.parse(init.body as string)).toEqual({
      source_id: "s1",
      scope_anchors: [],
      include_notes: true,
    });
  });

  it("raises the streaming failure type so a start failure reads like a stream failure", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(429, { detail: "slow down" }));
    await expect(
      startConversation(
        { sourceId: "s1", includeNotes: true },
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toBeInstanceOf(StreamRequestError);
  });
});

describe("listConversations", () => {
  it("narrows the list to one book and returns its summaries", async () => {
    const summary = { ...conversation, source_title: "A Book", turn_count: 3 };
    const fetchMock = vi.fn(async () => jsonResponse(200, [summary]));
    const rows = await listConversations(
      "s1",
      {},
      fetchMock as unknown as typeof fetch,
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].turn_count).toBe(3);
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/conversations?source_id=s1");
  });

  it("passes a requested page window through to the server", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, []));
    await listConversations(
      "s1",
      { limit: 5, offset: 10 },
      fetchMock as unknown as typeof fetch,
    );

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain("limit=5");
    expect(url).toContain("offset=10");
  });
});

describe("getConversation", () => {
  it("returns the conversation with its ordered turns", async () => {
    const detail = {
      ...conversation,
      turns: [
        {
          turn_index: 0,
          message: "a question",
          mode: "answer",
          answer_status: "answered",
          text: "an answer",
          citations: [],
          evidence_count: 4,
          model: "local-extractive",
          created_at: "now",
        },
      ],
    };
    const fetchMock = vi.fn(async () => jsonResponse(200, detail));
    const read = await getConversation(
      "conv1",
      fetchMock as unknown as typeof fetch,
    );

    expect(read.turns[0].message).toBe("a question");
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/conversations/conv1");
  });

  it("reports an absent conversation with its status so a caller can start fresh", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(404, { detail: "Conversation not found." }),
    );
    const err = await getConversation(
      "conv1",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ConversationRequestError);
    expect((err as ConversationRequestError).status).toBe(404);
    expect((err as Error).message).toBe("Conversation not found.");
  });
});

describe("renameConversation", () => {
  it("PATCHes the new title with the CSRF token", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...conversation, title: "Renamed" }),
    );
    const renamed = await renameConversation(
      "conv1",
      "Renamed",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(renamed.title).toBe("Renamed");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/conversations/conv1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ title: "Renamed" });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("surfaces a rejected title as a readable failure", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(422, { detail: [{ msg: "too long" }] }),
    );
    const err = await renameConversation(
      "conv1",
      "x".repeat(500),
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    // A FastAPI validation list is never rendered raw at the reader.
    expect((err as Error).message).toBe("Could not rename that conversation.");
    expect((err as ConversationRequestError).status).toBe(422);
  });
});

describe("deleteConversation", () => {
  it("DELETEs with the CSRF token and accepts an empty 204 body", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    await deleteConversation(
      "conv1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/conversations/conv1");
    expect(init.method).toBe("DELETE");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
  });
});
