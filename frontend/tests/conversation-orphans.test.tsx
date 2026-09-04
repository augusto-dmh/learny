// @vitest-environment jsdom

/**
 * A message that never landed must leave the thread behind, not take it away.
 *
 * Creating a conversation and sending its first message are two calls, so there
 * is a window where the first has succeeded and the second has not. That window
 * used to end in a DELETE: the client threw the conversation away rather than
 * leave an empty row in the dock. It no longer does — the reader's question is
 * the part worth keeping, so a failed or stopped first message keeps its
 * conversation and keeps the surface pointed at it, and the dock lists the row
 * once the server holds a turn for it. These tests drive the panel against a
 * fake server that actually holds what it was told to create, so the list
 * assertions are about what the server has, not about what the client drew.
 *
 * The contrast case still holds: a failure on a *later* message must not take
 * the thread with it either.
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

import { ReaderPanel } from "../app/components/reader-panel";
import { readActiveConversation } from "../app/lib/active-conversation";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
});


const CREATE_URL = "/api/conversations";
const CONVERSATION_URL = "/api/conversations/conv1";
const STREAM_URL = "/api/conversations/conv1/turns/stream";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * A fake server that remembers the conversations it was asked to create, so
 * "the dock will not list it" means the server no longer has it.
 */
function fakeServer(turnStream: (init: RequestInit) => Response) {
  const conversations = new Map<string, Record<string, unknown>>();
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "GET" && url.startsWith("/api/conversations?source_id=s1")) {
      // As the real list does: a conversation with no turn in it is not listed,
      // whatever the client did or failed to do about deleting it.
      return jsonResponse(
        200,
        [...conversations.values()].filter((row) => Number(row.turn_count) > 0),
      );
    }
    if (method === "POST" && url === CREATE_URL) {
      conversations.set("conv1", {
        id: "conv1",
        source_id: "s1",
        source_title: "A Book",
        title: "Untitled conversation",
        scope_anchors: [],
        include_notes: true,
        turn_count: 0,
        last_turn_mode: null,
        created_at: "now",
        updated_at: "now",
      });
      return jsonResponse(201, conversations.get("conv1"));
    }
    if (method === "POST" && url === STREAM_URL) {
      return turnStream(init ?? {});
    }
    if (method === "DELETE" && url === CONVERSATION_URL) {
      conversations.delete("conv1");
      return new Response(null, { status: 204 });
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { conversations, fetchMock };
}

/**
 * An SSE response that honours the request's abort signal the way a real fetch
 * body does — without it, stopping a stream in jsdom would never terminate it.
 */
function abortableStream(init: RequestInit) {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  init.signal?.addEventListener("abort", () => {
    controller.error(new DOMException("Aborted", "AbortError"));
  });
  const response = new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
  const push = (obj: unknown) =>
    act(async () => {
      controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  const close = () =>
    act(async () => {
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  return { response, push, close };
}

/**
 * A complete, answered turn on a stream that needs no abort handling.
 *
 * ``onPersisted`` runs as the last frame goes out, which is when the server would
 * have stored the turn — so a list read taken any earlier still sees a
 * conversation with nothing in it, exactly as a real one would mid-stream.
 */
function completedStream(onPersisted: () => void = () => {}) {
  const encoder = new TextEncoder();
  const frames = [
    { type: "start", messageId: "m1" },
    { type: "text-start", id: "t1" },
    { type: "text-delta", id: "t1", delta: "An answer." },
    { type: "text-end", id: "t1" },
    { type: "data-citations", data: [] },
    { type: "data-answer-status", data: { status: "answered" } },
    { type: "finish" },
  ];
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(frame)}\n\n`));
      }
      onPersisted();
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

function renderDock() {
  render(
    <ReaderPanel
      sourceId="s1"
      csrf="csrf-xyz"
      tab="chat"
      onTabChange={() => {}}
      onClose={() => {}}
    />,
  );
}

function ask(value: string) {
  fireEvent.change(screen.getByPlaceholderText(/ask a question/i), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

/** Every DELETE issued against the conversation the first message created. */
function deleteCalls(
  fetchMock: ReturnType<typeof fakeServer>["fetchMock"],
): unknown[][] {
  return fetchMock.mock.calls.filter(
    ([url, init]) =>
      url === CONVERSATION_URL &&
      (init as RequestInit | undefined)?.method === "DELETE",
  );
}

describe("a first message that does not land", () => {
  it("keeps the conversation when the turn fails", async () => {
    const { conversations, fetchMock } = fakeServer(() =>
      jsonResponse(429, { detail: "Too many requests." }),
    );
    renderDock();
    await screen.findByText("No conversations yet.");

    ask("a question that will be throttled");

    // The reader is told what happened.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);

    // And the conversation created for that message is still on the server,
    // still pointed at, so the reader retries into the same thread instead of
    // finding it gone.
    expect(conversations.has("conv1")).toBe(true);
    expect(deleteCalls(fetchMock)).toHaveLength(0);
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });

  it("keeps the conversation when the reader stops the turn", async () => {
    let stream: ReturnType<typeof abortableStream> | null = null;
    const { conversations, fetchMock } = fakeServer((init) => {
      stream = abortableStream(init);
      return stream.response;
    });
    renderDock();
    await screen.findByText("No conversations yet.");

    ask("a question I will interrupt");
    await waitFor(() => expect(stream).not.toBeNull());
    await stream!.push({ type: "start", messageId: "m1" });
    await stream!.push({ type: "text-start", id: "t1" });
    await stream!.push({ type: "text-delta", id: "t1", delta: "Partial" });

    const stopButton = await screen.findByRole("button", { name: "Stop" });
    await act(async () => {
      fireEvent.click(stopButton);
    });

    // Stopping is not a request to throw the question away.
    expect(conversations.has("conv1")).toBe(true);
    expect(deleteCalls(fetchMock)).toHaveLength(0);
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });

  it("lists the thread once its first message has landed, and not before", async () => {
    let stream: ReturnType<typeof abortableStream> | null = null;
    const { conversations } = fakeServer((init) => {
      stream = abortableStream(init);
      return stream.response;
    });
    renderDock();
    await screen.findByText("No conversations yet.");

    ask("a question I will let finish");
    await waitFor(() => expect(stream).not.toBeNull());
    await stream!.push({ type: "start", messageId: "m1" });
    await stream!.push({ type: "text-start", id: "t1" });
    await stream!.push({ type: "text-delta", id: "t1", delta: "An answer." });

    // Mid-stream the conversation exists but the server has no turn yet, so
    // there is nothing for the dock to offer the reader.
    await waitFor(() => expect(document.body.textContent).toContain("An answer."));
    expect(
      screen.queryByRole("button", { name: "Resume Untitled conversation" }),
    ).toBeNull();

    // The turn lands; from here the thread is something to come back to.
    const stored = conversations.get("conv1")!;
    conversations.set("conv1", {
      ...stored,
      turn_count: 1,
      last_turn_mode: "answer",
    });
    await stream!.push({ type: "text-end", id: "t1" });
    await stream!.push({ type: "data-citations", data: [] });
    await stream!.push({ type: "data-answer-status", data: { status: "answered" } });
    await stream!.push({ type: "finish" });
    await stream!.close();

    // The dock reads its list again, so the reader can find the thread without
    // reloading the page.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Resume Untitled conversation" }),
      ).toBeTruthy(),
    );
  });

  it("keeps the thread when a later message fails", async () => {
    let turns = 0;
    const { conversations, fetchMock } = fakeServer(() => {
      turns += 1;
      if (turns > 1) {
        return jsonResponse(429, { detail: "Too many requests." });
      }
      // The turn this stream carries is one the server keeps, so the conversation
      // stops being empty — which is what makes it something the dock can list.
      return completedStream(() => {
        const stored = conversations.get("conv1")!;
        conversations.set("conv1", {
          ...stored,
          turn_count: 1,
          last_turn_mode: "answer",
        });
      });
    });
    renderDock();
    await screen.findByText("No conversations yet.");

    // The first message lands, so its conversation is real.
    ask("a question that works");
    await waitFor(() => expect(document.body.textContent).toContain("An answer."));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Resume Untitled conversation" }),
      ).toBeTruthy(),
    );

    // A later failure is just a failed message — the thread survives it.
    ask("a question that gets throttled");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);

    expect(conversations.size).toBe(1);
    expect(deleteCalls(fetchMock)).toHaveLength(0);
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });
});
