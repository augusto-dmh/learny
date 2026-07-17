// @vitest-environment jsdom

/**
 * D3 gate (component) — the ask screen streams a grounded answer through the
 * same-origin proxy: it POSTs `{question}` with the CSRF header to the stream URL
 * (FE-06), renders text deltas progressively before the stream finishes (FE-07),
 * renders the terminal citations or the explicit not-found state (FE-08), settles
 * a mid-stream `error` part or a non-OK start (429) to a readable banner with
 * partial text retained and the input re-enabled (FE-09), disables submitting
 * while a stream is in flight, and never submits empty input (FE-10).
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

import { AskScreen } from "../app/components/ask-screen";

// AI Elements' Conversation (stick-to-bottom) and the citation Popover reach for
// ResizeObserver and pointer-capture APIs jsdom lacks; stub them.
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

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`; fail loudly on anything unexpected. */
function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

/** A UI Message Stream v1 SSE response whose frames the test pushes on demand. */
function sseStream() {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const response = new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
  // Enqueue one frame, then yield a macrotask inside `act` so the SDK consumes
  // the chunk and flushes its React state update before the next assertion.
  const frame = (bytes: Uint8Array) =>
    act(async () => {
      controller.enqueue(bytes);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  return {
    response,
    push: (obj: unknown) => frame(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`)),
    done: () => frame(encoder.encode("data: [DONE]\n\n")).then(() => controller.close()),
  };
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

const citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: "chapter-1.xhtml#core-idea",
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

const STREAM_URL = "/api/sources/s1/questions/stream";

function ask(value: string) {
  fireEvent.change(screen.getByPlaceholderText(/ask a question/i), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AskScreen streaming (D3)", () => {
  it("POSTs {question} with the CSRF header, streams deltas before finish, and renders citations", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);

    ask("Who wrote the first algorithm?");

    // FE-06: the request went to the stream URL with the exact body and CSRF header.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => url === STREAM_URL)!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      question: "Who wrote the first algorithm?",
    });
    expect(new Headers((call[1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );

    // FE-07: a first delta is visible before the stream finishes.
    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Ada Lovelace " });
    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace"),
    );
    expect(document.body.textContent).not.toContain("first algorithm ever");

    // FE-08: the rest streams, then the terminal citations render.
    await stream.push({
      type: "text-delta",
      id: "t1",
      delta: "wrote the first algorithm.",
    });
    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "data-citations", data: [citation] });
    await stream.push({
      type: "data-answer-status",
      data: { status: "answered" },
    });
    await stream.push({ type: "finish" });
    await stream.done();

    await waitFor(() =>
      expect(document.body.textContent).toContain(
        "Ada Lovelace wrote the first algorithm.",
      ),
    );
    // The citation renders as an "open in book" chip (breadcrumb from section_path).
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    ).toBeTruthy();
  });

  it("renders the not-found state with no citations on not_found_in_source", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`POST ${STREAM_URL}`]: () => stream.response,
      }),
    );

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);
    ask("nonsense token");
    await waitFor(() =>
      expect(document.body.textContent).toContain("nonsense token"),
    );

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "data-citations", data: [] });
    await stream.push({
      type: "data-answer-status",
      data: { status: "not_found_in_source" },
    });
    await stream.push({ type: "finish" });
    await stream.done();

    const notFound = await screen.findByTestId("not-found");
    expect(notFound.textContent).toContain("not found in this source");
    // No citation chips are rendered for a not-found answer.
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("settles a mid-stream error part to a banner, retaining partial text and re-enabling input", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`POST ${STREAM_URL}`]: () => stream.response,
      }),
    );

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);
    ask("first try");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Partial answer" });
    await waitFor(() =>
      expect(document.body.textContent).toContain("Partial answer"),
    );
    // The error part terminates the stream; the SDK surfaces it via onError.
    await stream.push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    // Readable banner, partial text retained, input usable again.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Answer generation failed");
    expect(document.body.textContent).toContain("Partial answer");
    expect(
      (screen.getByPlaceholderText(/ask a question/i) as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);
  });

  it("shows a readable throttle message when the stream start returns 429", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`POST ${STREAM_URL}`]: () =>
          jsonResponse(429, { detail: "Too many requests." }),
      }),
    );

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);
    ask("a question");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
    expect(
      (screen.getByPlaceholderText(/ask a question/i) as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);
  });

  it("swaps submit for a stop control while streaming and issues only one request", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);
    ask("streaming question");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Streaming…" });

    // Mid-stream the submit control is a Stop button — you cannot submit again.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy(),
    );
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
    expect(
      fetchMock.mock.calls.filter(([url]) => url === STREAM_URL),
    ).toHaveLength(1);

    await stream.done();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Stop" })).toBeNull(),
    );
  });

  it("never submits when the input is empty", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`POST ${STREAM_URL}`]: () => sseStream().response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskScreen sourceId="s1" />);
    await screen.findByPlaceholderText(/ask a question/i);

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    // No stream request is issued for an empty question.
    await Promise.resolve();
    expect(
      fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
    ).toBe(false);
  });
});

describe("AskScreen auth (D3)", () => {
  it("does a UX-only redirect and shows the signed-out state when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<AskScreen sourceId="s1" onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});
