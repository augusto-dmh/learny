// @vitest-environment jsdom

/**
 * The Ask panel runs on the unified conversation surface. A question in a book
 * with no active thread creates a whole-book conversation and posts the question
 * as its first turn; every question after it streams straight into that same
 * conversation, so only one conversation is ever created for a thread.
 *
 * Everything the reader sees is unchanged by that move: text deltas render
 * progressively, the terminal citations or the explicit not-found state render
 * at the end, a mid-stream `error` part or a non-OK start settles to a readable
 * banner with partial text retained and the input re-enabled, submit swaps for
 * stop while streaming, empty input never submits, and a 401 routes to
 * `onRequireAuth`.
 *
 * Panel-only behavior: suggested prompts in the empty state that submit on click
 * (RA-08), a streaming caret at the tail of the in-flight answer (RA-09), and the
 * selection-verb contract — an `explain` pending request auto-submits a fixed
 * template around the quote (RA-17) and an `ask` pending request attaches the
 * quote as context that rides along with the typed question (RA-18).
 *
 * Auth is resolved upstream in the reader, so the panel takes the CSRF token as a
 * prop — these tests never stub `/api/auth/me`.
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

import { AskPanel } from "../app/components/ask-panel";
import {
  readActiveConversation,
  writeActiveConversation,
} from "../app/lib/active-conversation";

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

const citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: "chapter-1.xhtml#core-idea",
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

const CREATE_URL = "/api/conversations";
const STREAM_URL = "/api/conversations/conv1/turns/stream";

const conversation = {
  id: "conv1",
  source_id: "s1",
  title: "Untitled conversation",
  scope_anchors: [],
  include_notes: true,
  created_at: "now",
  updated_at: "now",
};

/** The create + stream pair every question needs, plus anything extra. */
function baseHandlers(
  stream: () => Response,
  extra: Record<string, Handler> = {},
): Record<string, Handler> {
  return {
    [`POST ${CREATE_URL}`]: () => jsonResponse(201, conversation),
    [`POST ${STREAM_URL}`]: () => stream(),
    ...extra,
  };
}

function bodyOf(call: unknown[]): Record<string, unknown> {
  return JSON.parse((call[1] as RequestInit).body as string);
}

function callsTo(
  fetchMock: ReturnType<typeof routedFetch>,
  url: string,
): unknown[][] {
  return fetchMock.mock.calls.filter(([called]) => called === url);
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

describe("AskPanel on the conversation surface", () => {
  it("creates a whole-book conversation, posts the question as its first turn, and renders citations", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    ask("Who wrote the first algorithm?");

    // The conversation is created for this book with whole-book scope.
    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    const create = callsTo(fetchMock, CREATE_URL)[0];
    expect(bodyOf(create)).toMatchObject({
      source_id: "s1",
      scope_anchors: [],
    });
    expect(new Headers((create[1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );

    // The question is then posted as an answer-mode turn on that conversation.
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));
    const turn = callsTo(fetchMock, STREAM_URL)[0];
    expect(bodyOf(turn)).toEqual({
      message: "Who wrote the first algorithm?",
      mode: "answer",
    });
    expect(new Headers((turn[1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );

    // A first delta is visible before the stream finishes.
    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Ada Lovelace " });
    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace"),
    );
    expect(document.body.textContent).not.toContain("first algorithm ever");

    // The rest streams, then the terminal citations render.
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

  it("continues the same conversation for a follow-up instead of creating a second one", async () => {
    const streams: ReturnType<typeof sseStream>[] = [];
    const fetchMock = routedFetch(
      baseHandlers(() => {
        const next = sseStream();
        streams.push(next);
        return next.response;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    ask("first question");
    await waitFor(() => expect(streams).toHaveLength(1));
    await streamAnswer(streams[0], []);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy(),
    );

    ask("a follow-up");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(2));

    // Exactly one conversation exists; the follow-up rides the same one.
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[1])).toEqual({
      message: "a follow-up",
      mode: "answer",
    });
  });

  it("renders the whole-book not-found state with no citations", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
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
    expect(notFound.textContent).toContain("not found in this book");
    // No citation chips are rendered for a not-found answer.
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("settles a mid-stream error part to a banner, retaining partial text and re-enabling input", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => stream.response, {
          "DELETE /api/conversations/conv1": () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
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

  it("shows a readable throttle message when the turn stream returns 429", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => jsonResponse(429, { detail: "Too many requests." }), {
          "DELETE /api/conversations/conv1": () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
    expect(
      (screen.getByPlaceholderText(/ask a question/i) as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);
  });

  it("swaps submit for a stop control while streaming and issues only one turn", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("streaming question");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Streaming…" });

    // Mid-stream the submit control is a Stop button — you cannot submit again.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy(),
    );
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
    expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1);

    await stream.done();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Stop" })).toBeNull(),
    );
  });

  it("never submits when the input is empty", async () => {
    const fetchMock = routedFetch(baseHandlers(() => sseStream().response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    // Neither a conversation nor a turn is created for an empty question.
    await Promise.resolve();
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(0);
    expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(0);
  });
});

describe("AskPanel notes scope (NL-04)", () => {
  it("carries the reader's notes choice into the conversation it creates", async () => {
    const fetchMock = routedFetch(baseHandlers(() => sseStream().response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    // The control reflects the Q&A default (on) before any choice.
    const toggle = screen.getByRole("checkbox", { name: "Search my notes too" });
    expect((toggle as HTMLInputElement).checked).toBe(true);

    // Turning it off is carried into the conversation the question creates.
    fireEvent.click(toggle);
    ask("a question");

    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      include_notes: false,
    });
  });

  it("states the choice on the wire even when the reader never touched it", async () => {
    const fetchMock = routedFetch(baseHandlers(() => sseStream().response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    // The server has no default to fall back on, so the flag is never omitted.
    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toHaveProperty(
      "include_notes",
      true,
    );
  });

  it("stops taking a choice once the thread has a conversation, and says why", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    const toggle = () =>
      screen.getByRole("checkbox", {
        name: "Search my notes too",
      }) as HTMLInputElement;

    // Before there is a conversation the choice is the reader's to make.
    expect(toggle().disabled).toBe(false);
    fireEvent.click(toggle());
    ask("a question");
    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));

    // Once one exists the control reports what it was created with and stops
    // being flippable — the flip would have applied to nothing.
    await waitFor(() => expect(toggle().disabled).toBe(true));
    expect(toggle().checked).toBe(false);
    const description = document.getElementById(
      toggle().getAttribute("aria-describedby")!,
    );
    expect(description!.textContent).toMatch(/start a new one to change it/i);
  });

  it("reports a restored conversation's choice, not the reader's stored one", async () => {
    // The reader's preference for this surface is on; the thread they are coming
    // back to was created with it off, and the thread is what the answer obeys.
    const fetchMock = routedFetch({
      "GET /api/conversations/conv1": () =>
        jsonResponse(200, {
          ...conversation,
          include_notes: false,
          turns: [],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "ask", "conv1");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    const toggle = (await screen.findByRole("checkbox", {
      name: "Search my notes too",
    })) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(toggle.disabled).toBe(true);
  });
});

describe("AskPanel thread restore", () => {
  const READ_URL = "/api/conversations/conv1";

  it("restores an active thread's turns from the server after a reload", async () => {
    // First visit: ask a question and let the turn land, so this book's Ask
    // surface is left pointing at the conversation the server created.
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));
    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("Who wrote the first algorithm?");
    await streamAnswer(stream, [citation]);
    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace did."),
    );

    // The reload: a brand-new tree with nothing carried over from the last one.
    cleanup();
    vi.restoreAllMocks();

    // The server is the only place the thread exists, and what it holds is not
    // what the previous tree rendered — so anything replayed from the browser
    // would be visibly wrong.
    const restored = {
      ...conversation,
      turns: [
        {
          turn_index: 0,
          message: "Who wrote the first algorithm?",
          mode: "answer",
          answer_status: "answered",
          text: "The server's copy of the answer.",
          citations: [citation],
          evidence_count: 6,
          model: "local-extractive",
          created_at: "now",
        },
      ],
    };
    const fetchMock = routedFetch({
      [`GET ${READ_URL}`]: () => jsonResponse(200, restored),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    // The thread comes back, read from the server.
    expect(
      await screen.findByText("The server's copy of the answer."),
    ).toBeTruthy();
    expect(screen.getByText("Who wrote the first algorithm?")).toBeTruthy();
    expect(callsTo(fetchMock, READ_URL)).toHaveLength(1);
    // A restored thread is a thread, so the empty state is gone.
    expect(screen.queryByLabelText("suggested prompts")).toBeNull();
    // Its citations come back with it.
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    ).toBeTruthy();
  });

  it("continues the restored conversation instead of creating a new one", async () => {
    const restored = { ...conversation, turns: [] };
    const stream = sseStream();
    const fetchMock = routedFetch({
      [`GET ${READ_URL}`]: () => jsonResponse(200, restored),
      ...baseHandlers(() => stream.response),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "ask", "conv1");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await waitFor(() => expect(callsTo(fetchMock, READ_URL)).toHaveLength(1));

    ask("a follow-up after the reload");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    // The restored conversation is continued; nothing new is created.
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(0);
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message: "a follow-up after the reload",
      mode: "answer",
    });
  });

  it("starts a fresh thread when the remembered conversation is gone", async () => {
    const fetchMock = routedFetch({
      [`GET ${READ_URL}`]: () =>
        jsonResponse(404, { detail: "Conversation not found." }),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "ask", "conv1");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    // A pointer that outlived its conversation is not an error the reader sees —
    // it simply means there is no thread to come back to.
    expect(await screen.findByLabelText("suggested prompts")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });
});

describe("AskPanel when the conversation cannot be created", () => {
  /**
   * Only the create leg is routed: a stream attempt would mean the panel tried
   * to post a turn into a conversation the server never made, and `routedFetch`
   * fails loudly on it.
   */
  function failingCreate(status: number, detail: string) {
    const fetchMock = routedFetch({
      [`POST ${CREATE_URL}`]: () => jsonResponse(status, { detail }),
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("tells the reader a book that is still processing is not ready (409)", async () => {
    const fetchMock = failingCreate(409, "Source is not ready.");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question about a book still being ingested");

    // The failure is on screen, in the reader's terms.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/still processing/i);

    // And the panel is usable again rather than left spinning: the control is
    // back to Submit, there is no streaming caret, and the input is not disabled.
    expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(screen.queryByTestId("streaming-caret")).toBeNull();
    expect(
      (screen.getByPlaceholderText(/ask a question/i) as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);

    // Nothing was created, so nothing is pointed at and nothing needs cleaning up.
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(fetchMock.mock.calls).toHaveLength(1);
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });

  it("shows a readable throttle message when the create is throttled (429)", async () => {
    failingCreate(429, "Too many requests.");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
    expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy();
  });

  it("says the book could not be found when the create 404s", async () => {
    failingCreate(404, "Source not found.");

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question about a book that is gone");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not be found/i);
    expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy();
  });

  it("routes an expired session on the create leg to onRequireAuth (401)", async () => {
    failingCreate(401, "Not authenticated.");

    const onRequireAuth = vi.fn();
    render(
      <AskPanel sourceId="s1" csrf="csrf-xyz" onRequireAuth={onRequireAuth} />,
    );
    ask("a question");

    // Same contract as a 401 mid-stream: a redirect, not an inline banner.
    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("AskPanel auth (RA-07)", () => {
  it("routes a 401 turn stream to onRequireAuth without a banner", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => new Response(null, { status: 401 }), {
          "DELETE /api/conversations/conv1": () => new Response(null, { status: 204 }),
        }),
      ),
    );

    const onRequireAuth = vi.fn();
    render(
      <AskPanel sourceId="s1" csrf="csrf-xyz" onRequireAuth={onRequireAuth} />,
    );
    ask("a question");

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    // A 401 is a UX redirect, not an inline error banner.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("AskPanel suggested prompts (RA-08)", () => {
  it("shows suggested prompts only when empty and submits the clicked one", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    // The empty state offers a fixed set of suggested prompts.
    const suggestions = screen.getByLabelText("suggested prompts");
    const prompts = Array.from(suggestions.querySelectorAll("button"));
    expect(prompts).toHaveLength(3);
    const chosen = prompts[0].textContent!;

    fireEvent.click(prompts[0]);

    // Clicking a prompt submits it verbatim as a question.
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message: chosen,
      mode: "answer",
    });

    // Once a message exists the empty-state prompts are gone.
    await waitFor(() =>
      expect(screen.queryByLabelText("suggested prompts")).toBeNull(),
    );
  });
});

describe("AskPanel streaming caret (RA-09)", () => {
  it("shows a caret while the answer streams and removes it on finish", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Answering" });

    // The caret marks the tail of the in-flight answer.
    await waitFor(() =>
      expect(screen.getByTestId("streaming-caret")).toBeTruthy(),
    );

    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "finish" });
    await stream.done();

    // It disappears once the message completes.
    await waitFor(() =>
      expect(screen.queryByTestId("streaming-caret")).toBeNull(),
    );
  });
});

describe("AskPanel answer phases (ANSW-01/02/03)", () => {
  /** The phase line, wherever in the thread it is currently rendered. */
  function phaseLine(): HTMLElement | null {
    return screen.queryByText(/searching the book/i);
  }

  function reasoningRegion(): HTMLElement | null {
    return screen.queryByRole("region", { name: "reasoning" });
  }

  it("shows the search phase from submit until the model starts, then the thinking, then the answer", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("Who wrote the first algorithm?");

    // The wait starts at submit — before a single frame has come back, which is
    // exactly the stretch that used to be blank.
    await waitFor(() => expect(phaseLine()).toBeTruthy());
    expect(phaseLine()!.textContent).toContain("Searching the book");

    // The backend's own searching frame reads the same, so the phase does not
    // flicker between the request going out and the search being announced.
    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "data-phase", data: { phase: "searching" } });
    expect(phaseLine()!.textContent).toContain("Searching the book");
    expect(reasoningRegion()).toBeNull();

    // The model starts thinking: the search line gives way to the live reasoning,
    // open and streaming its text.
    await stream.push({ type: "reasoning-start", id: "r1" });
    await stream.push({
      type: "reasoning-delta",
      id: "r1",
      delta: "The chapter on engines ",
    });
    await stream.push({
      type: "reasoning-delta",
      id: "r1",
      delta: "names her.",
    });

    await waitFor(() => expect(reasoningRegion()).toBeTruthy());
    expect(phaseLine()).toBeNull();
    expect(
      screen.getByText("The chapter on engines names her."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /thinking/i })).toBeTruthy();

    // The answer arrives: the thinking folds away on its own, leaving the answer.
    await stream.push({ type: "reasoning-end", id: "r1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Ada Lovelace did." });

    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace did."),
    );
    expect(screen.queryByText("The chapter on engines names her.")).toBeNull();
    expect(reasoningRegion()).toBeTruthy();

    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "data-citations", data: [citation] });
    await stream.push({
      type: "data-answer-status",
      data: { status: "answered" },
    });
    await stream.push({ type: "finish" });
    await stream.done();

    // The completed turn keeps its thinking available — collapsed, and reopenable
    // for as long as the turn is on screen.
    const toggle = await screen.findByRole("button", {
      name: /thought process/i,
    });
    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(screen.getByText("The chapter on engines names her.")).toBeTruthy();
    expect(phaseLine()).toBeNull();
  });

  it("skips the reasoning region entirely for a turn that carried no thinking", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    // The local adapter — and any turn adaptive thinking skipped — streams text
    // with no reasoning at all. There is no shell for the reader to open.
    await streamAnswer(stream, [citation]);

    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace did."),
    );
    expect(reasoningRegion()).toBeNull();
    expect(phaseLine()).toBeNull();
  });

  it("collapses a not-found turn's thinking into the not-found notice", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("nonsense token");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "data-phase", data: { phase: "searching" } });
    await stream.push({ type: "reasoning-start", id: "r1" });
    await stream.push({
      type: "reasoning-delta",
      id: "r1",
      delta: "Nothing in the book covers this.",
    });
    await stream.push({ type: "reasoning-end", id: "r1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "data-citations", data: [] });
    await stream.push({
      type: "data-answer-status",
      data: { status: "not_found_in_source" },
    });
    await stream.push({ type: "finish" });
    await stream.done();

    // The verdict stands alone: no reasoning left beside a retraction of it.
    const notFound = await screen.findByTestId("not-found");
    expect(notFound.textContent).toContain("not found in this book");
    expect(reasoningRegion()).toBeNull();
    expect(phaseLine()).toBeNull();
    expect(
      screen.queryByText("Nothing in the book covers this."),
    ).toBeNull();
  });

  it("replaces the phase line with the error state when the stream fails mid-search", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => stream.response, {
          "DELETE /api/conversations/conv1": () =>
            new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "data-phase", data: { phase: "searching" } });
    await waitFor(() => expect(phaseLine()).toBeTruthy());

    // Retrieval now runs inside the stream, so its failure arrives as an error
    // part rather than a pre-stream status — and it must end the waiting.
    await stream.push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/generation failed/i);
    await waitFor(() => expect(phaseLine()).toBeNull());
  });

  it("shows no reasoning region on a restored thread", async () => {
    // Thinking is transient, so a thread read back from the server has none —
    // and must not render an empty region where it used to be.
    const restored = {
      ...conversation,
      turns: [
        {
          turn_index: 0,
          message: "Who wrote the first algorithm?",
          mode: "answer",
          answer_status: "answered",
          text: "The server's copy of the answer.",
          citations: [citation],
          evidence_count: 6,
          model: "local-extractive",
          created_at: "now",
        },
      ],
    };
    writeActiveConversation("s1", "ask", "conv1");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/conversations/conv1": () => jsonResponse(200, restored),
      }),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    expect(
      await screen.findByText("The server's copy of the answer."),
    ).toBeTruthy();
    expect(reasoningRegion()).toBeNull();
    expect(phaseLine()).toBeNull();
  });
});

const noteDetail = {
  id: "n1",
  title: "note",
  body_markdown: "body",
  tags: [],
  anchors: [],
  created_at: "now",
  updated_at: "now",
};

const HIGHLIGHTS_URL = "/api/sources/s1/highlights";
const NOTES_URL = "/api/notes";

/** Stream a complete, answered turn carrying `citations` and settling the stream. */
async function streamAnswer(
  stream: ReturnType<typeof sseStream>,
  citations: unknown[],
) {
  await stream.push({ type: "start", messageId: "m1" });
  await stream.push({ type: "text-start", id: "t1" });
  await stream.push({ type: "text-delta", id: "t1", delta: "Ada Lovelace did." });
  await stream.push({ type: "text-end", id: "t1" });
  await stream.push({ type: "data-citations", data: citations });
  await stream.push({ type: "data-answer-status", data: { status: "answered" } });
  await stream.push({ type: "finish" });
  await stream.done();
}

describe("AskPanel save to note (RA-20/22)", () => {
  it("offers Save to note on a cited answer and confirms success", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(
      baseHandlers(() => stream.response, {
        [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, noteDetail),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("Who wrote the first algorithm?");
    await streamAnswer(stream, [citation]);

    // A cited, completed answer offers the save action.
    const saveButton = await screen.findByRole("button", {
      name: "Save to note",
    });
    await act(async () => {
      fireEvent.click(saveButton);
    });

    // The action drives the capture endpoint and confirms success in the UI.
    await waitFor(() =>
      expect(callsTo(fetchMock, HIGHLIGHTS_URL)).toHaveLength(1),
    );
    expect(await screen.findByTestId("save-note-status")).toBeTruthy();
  });

  it("still saves the answer, anchored, through the real notes clients on a stale capture (409)", async () => {
    const stream = sseStream();
    let captures = 0;
    const fetchMock = routedFetch(
      baseHandlers(() => stream.response, {
        // The quoted capture cannot bind; the quote-less one on the same anchor can.
        [`POST ${HIGHLIGHTS_URL}`]: () =>
          ++captures === 1
            ? jsonResponse(409, {
                detail: "The book changed while you were reading.",
              })
            : jsonResponse(201, noteDetail),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("Who wrote the first algorithm?");
    await streamAnswer(stream, [citation]);

    const saveButton = await screen.findByRole("button", {
      name: "Save to note",
    });
    await act(async () => {
      fireEvent.click(saveButton);
    });

    // The answer survives the conflict and is still filed against the passage's
    // anchor — exercised through the real lib/notes clients, not fakes.
    await waitFor(() =>
      expect(callsTo(fetchMock, HIGHLIGHTS_URL)).toHaveLength(2),
    );
    const body = bodyOf(callsTo(fetchMock, HIGHLIGHTS_URL)[1]);
    expect(body.body_markdown).toContain("Ada Lovelace did.");
    expect(body.quote_exact).toBe("");
    expect(body.anchor).toBe(citation.anchor);
    // Nothing was posted to the rootless notes collection.
    expect(callsTo(fetchMock, NOTES_URL)).toHaveLength(0);
    expect(await screen.findByTestId("save-note-status")).toBeTruthy();
  });

  it("shows an inline error and no confirmation when saving fails", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => stream.response, {
          [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(500, { detail: "boom" }),
        }),
      ),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");
    await streamAnswer(stream, [citation]);

    const saveButton = await screen.findByRole("button", {
      name: "Save to note",
    });
    await act(async () => {
      fireEvent.click(saveButton);
    });

    const error = await screen.findByTestId("save-note-error");
    expect(error.textContent).toContain("Could not save");
    expect(screen.queryByTestId("save-note-status")).toBeNull();
  });

  it("does not offer Save to note on a not-found answer", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("nonsense token");
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

    await screen.findByTestId("not-found");
    expect(
      screen.queryByRole("button", { name: "Save to note" }),
    ).toBeNull();
  });

  it("does not offer Save to note on an answered response with no citations", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    ask("a question");
    await streamAnswer(stream, []);

    await waitFor(() =>
      expect(document.body.textContent).toContain("Ada Lovelace did."),
    );
    expect(
      screen.queryByRole("button", { name: "Save to note" }),
    ).toBeNull();
  });
});

describe("AskPanel selection verbs (RA-17/18)", () => {
  it("auto-submits the fixed Explain template for an explain pending request", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    const onPendingConsumed = vi.fn();
    render(
      <AskPanel
        sourceId="s1"
        csrf="csrf-xyz"
        pendingRequest={{
          kind: "explain",
          quote: "the selected sentence",
          anchor: "c1.xhtml#s1",
        }}
        onPendingConsumed={onPendingConsumed}
      />,
    );

    // The explain verb submits, one tap, with the exact fixed template.
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message: 'Explain this passage from the book:\n\n"the selected sentence"',
      mode: "answer",
    });
    // The request is consumed exactly once, so it never re-submits.
    expect(onPendingConsumed).toHaveBeenCalledTimes(1);
    expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1);
  });

  it("attaches the quote as context and submits it with the typed question", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    const onPendingConsumed = vi.fn();
    render(
      <AskPanel
        sourceId="s1"
        csrf="csrf-xyz"
        pendingRequest={{
          kind: "ask",
          quote: "a quoted passage",
          anchor: "c1.xhtml#s1",
        }}
        onPendingConsumed={onPendingConsumed}
      />,
    );

    // An ask verb stows the quote as a visible context chip, consumed once, and
    // does NOT submit on its own.
    const chip = await screen.findByTestId("ask-context-chip");
    expect(chip.textContent).toContain("a quoted passage");
    expect(onPendingConsumed).toHaveBeenCalledTimes(1);
    expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(0);

    // The typed question rides along with the attached quote in the fixed shape.
    ask("What does this mean?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message:
        'Regarding this passage:\n\n"a quoted passage"\n\nWhat does this mean?',
      mode: "answer",
    });
  });

  it("submits a bare question after the attached passage is removed", async () => {
    const fetchMock = routedFetch(baseHandlers(() => sseStream().response));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AskPanel
        sourceId="s1"
        csrf="csrf-xyz"
        pendingRequest={{
          kind: "ask",
          quote: "a quoted passage",
          anchor: "c1.xhtml#s1",
        }}
      />,
    );

    // Dismiss the attached passage before typing anything.
    await screen.findByTestId("ask-context-chip");
    fireEvent.click(
      screen.getByRole("button", { name: "Remove attached passage" }),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("ask-context-chip")).toBeNull(),
    );

    // The typed question submits unwrapped — the discarded passage never rides along.
    ask("What does this mean?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message: "What does this mean?",
      mode: "answer",
    });
  });

  it("does not re-attach the quote to a second question after a combined submit", async () => {
    const streams: ReturnType<typeof sseStream>[] = [];
    const fetchMock = routedFetch(
      baseHandlers(() => {
        const next = sseStream();
        streams.push(next);
        return next.response;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AskPanel
        sourceId="s1"
        csrf="csrf-xyz"
        pendingRequest={{
          kind: "ask",
          quote: "a quoted passage",
          anchor: "c1.xhtml#s1",
        }}
      />,
    );
    await screen.findByTestId("ask-context-chip");

    // The first typed question rides along with the attached quote.
    ask("What does this mean?");
    await waitFor(() => expect(streams).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[0])).toEqual({
      message:
        'Regarding this passage:\n\n"a quoted passage"\n\nWhat does this mean?',
      mode: "answer",
    });
    await streamAnswer(streams[0], []);
    // Wait for the stream to settle so the input accepts a fresh submit.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy(),
    );

    // A second question submits bare — the quote was consumed once, not made sticky.
    ask("And now?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(2));
    expect(bodyOf(callsTo(fetchMock, STREAM_URL)[1])).toEqual({
      message: "And now?",
      mode: "answer",
    });
  });
});
