// @vitest-environment jsdom

/**
 * The Teach panel runs on the unified conversation surface. Picking a target and
 * sending the first message creates a conversation scoped to that target's
 * anchor and posts the message as a taught turn; every message after it
 * continues the same conversation. A thread this book's Teach surface is pointed
 * at is restored from the server, with its stored turns and their citations.
 *
 * Everything the reader sees is unchanged by that move: deltas render
 * progressively, the terminal citations or the explicit not-found state render
 * at the end, and a throttle (429), a mid-stream error, or a 401 settle to the
 * same readable state contract as Ask.
 *
 * Panel-only behavior: when a session activates — on start AND on restore — the
 * panel calls `onShowInBook` exactly once with the taught anchor, never per turn
 * (RA-11).
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

import { TeachPanel } from "../app/components/teach-panel";
import { writeActiveConversation } from "../app/lib/active-conversation";

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

const structure = {
  title: "Ready Book",
  authors: ["Ada Lovelace"],
  language: "en",
  sections: [
    {
      title: "Chapter 1",
      depth: 0,
      section_path: ["Chapter 1"],
      anchor: "c1.xhtml",
      children: [
        {
          title: "Section 1.1",
          depth: 1,
          section_path: ["Chapter 1", "Section 1.1"],
          anchor: "c1.xhtml#s1",
          children: [],
        },
      ],
    },
    {
      title: "Chapter 2",
      depth: 0,
      section_path: ["Chapter 2"],
      anchor: "c2.xhtml",
      children: [],
    },
  ],
};

const citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 2", "Overview"],
  anchor: "c2.xhtml#overview",
  page_span: null,
  snippet: "a note on the analytical engine",
  score: 0.02,
};

const CREATE_URL = "/api/conversations";
const READ_URL = "/api/conversations/conv2";
const TURN_STREAM = "/api/conversations/conv2/turns/stream";

function conversationScopedTo(anchor: string, title: string) {
  return {
    id: "conv2",
    source_id: "s1",
    title,
    scope_anchors: [anchor],
    include_notes: false,
    created_at: "now",
    updated_at: "now",
  };
}

/** A restored thread's stored, ordered, cited history. */
const restoredDetail = {
  ...conversationScopedTo("c1.xhtml", "Chapter 1"),
  turns: [
    {
      turn_index: 0,
      message: "What is this about?",
      mode: "teach",
      answer_status: "answered",
      text: "It is about early computing.",
      citations: [
        {
          chunk_id: "c9",
          source_id: "s1",
          section_path: ["Chapter 1", "Intro"],
          anchor: "c1.xhtml#intro",
          page_span: null,
          snippet: "early computing history",
          score: 0.05,
        },
      ],
      evidence_count: 8,
      model: "local-extractive",
      created_at: "now",
    },
    {
      turn_index: 1,
      message: "and the weather?",
      mode: "teach",
      answer_status: "not_found_in_scope",
      text: "",
      citations: [],
      evidence_count: 0,
      model: "local-extractive",
      created_at: "now",
    },
  ],
};

function baseHandlers(
  stream: () => Response,
  extra: Record<string, Handler> = {},
): Record<string, Handler> {
  return {
    "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
    [`POST ${CREATE_URL}`]: () =>
      jsonResponse(201, conversationScopedTo("c2.xhtml", "Chapter 2")),
    [`POST ${TURN_STREAM}`]: () => stream(),
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

function sendMessage(value: string) {
  fireEvent.change(screen.getByPlaceholderText(/send a message/i), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
}

/** Pick a target and enter the taught thread. */
async function startSession(anchor = "c2.xhtml") {
  await screen.findByLabelText("Target");
  await screen.findByRole("option", { name: "Chapter 1" }, { timeout: 5000 });
  fireEvent.change(screen.getByLabelText("Target"), { target: { value: anchor } });
  fireEvent.click(screen.getByRole("button", { name: "Start session" }));
  await screen.findByPlaceholderText(/send a message/i, {}, { timeout: 5000 });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("TeachPanel on the conversation surface (RA-10)", () => {
  it("scopes a new conversation to the chosen target and streams a taught turn", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);

    // Every flattened section (incl. the nested one as a breadcrumb) is offered.
    await screen.findByLabelText("Target");
    await screen.findByRole("option", { name: "Chapter 1" }, { timeout: 5000 });
    expect(
      screen.getByRole("option", { name: "Chapter 1 › Section 1.1" }),
    ).toBeTruthy();
    expect(screen.getByRole("option", { name: "Chapter 2" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "c2.xhtml" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByPlaceholderText(/send a message/i, {}, { timeout: 5000 });

    // Nothing is created until there is something to teach.
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(0);

    sendMessage("Explain this chapter.");

    // The conversation is scoped to the chosen target and named for it.
    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      source_id: "s1",
      scope_anchors: ["c2.xhtml"],
      title: "Chapter 2",
    });

    // The message is posted as a taught turn on that conversation.
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(1));
    const turnPost = callsTo(fetchMock, TURN_STREAM)[0];
    expect(bodyOf(turnPost)).toEqual({
      message: "Explain this chapter.",
      mode: "teach",
    });
    expect(
      new Headers((turnPost[1] as RequestInit).headers).get("X-CSRF-Token"),
    ).toBe("csrf-xyz");

    // Deltas render progressively before the terminal citations.
    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "The chapter " });
    await waitFor(() =>
      expect(document.body.textContent).toContain("The chapter"),
    );
    await stream.push({
      type: "text-delta",
      id: "t1",
      delta: "introduces the analytical engine.",
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
        "The chapter introduces the analytical engine.",
      ),
    );
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 2 › Overview" }),
    ).toBeTruthy();
  });

  it("continues the same conversation for a second message", async () => {
    const streams: ReturnType<typeof sseStream>[] = [];
    const fetchMock = routedFetch(
      baseHandlers(() => {
        const next = sseStream();
        streams.push(next);
        return next.response;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();

    sendMessage("first message");
    await waitFor(() => expect(streams).toHaveLength(1));
    await streamTurn(streams[0], []);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy(),
    );

    sendMessage("second message");
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(2));

    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
  });

  it("renders the whole-book not-found state with no citations", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("unrelated nonsense");

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
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("shows a readable throttle message when a turn stream returns 429", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => jsonResponse(429, { detail: "Too many requests." }), {
          [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("a message");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
  });

  it("keeps the reader in the session when the conversation cannot be created", async () => {
    // Only the structure and the create leg are routed: a stream attempt would
    // mean a turn was posted into a conversation the server never made, and
    // `routedFetch` fails loudly on it.
    const fetchMock = routedFetch({
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      [`POST ${CREATE_URL}`]: () =>
        jsonResponse(409, { detail: "Source is not ready." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("teach me this section");

    // The failure is readable, and the panel is usable again rather than left
    // spinning on a message that never went anywhere.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/still processing/i);
    expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(
      (screen.getByPlaceholderText(/send a message/i) as HTMLTextAreaElement)
        .disabled,
    ).toBe(false);

    // Nothing was created, so there is nothing to point at or clean up.
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
  });

  it("settles a mid-stream error part to a banner with partial text retained", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => stream.response, {
          [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("first try");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "Partial turn" });
    await waitFor(() =>
      expect(document.body.textContent).toContain("Partial turn"),
    );
    await stream.push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Answer generation failed");
    expect(document.body.textContent).toContain("Partial turn");
  });
});

describe("TeachPanel scope misses", () => {
  it("says the answer may be elsewhere in the book when the scope comes up empty", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("something from another chapter");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-end", id: "t1" });
    await stream.push({ type: "data-citations", data: [] });
    await stream.push({
      type: "data-answer-status",
      data: { status: "not_found_in_scope" },
    });
    await stream.push({ type: "finish" });
    await stream.done();

    // The reader is told the scope came up short, not that the book did.
    const notFound = await screen.findByTestId("not-found");
    expect(notFound.textContent).toMatch(/elsewhere in the book/i);
    expect(notFound.textContent).not.toMatch(/^That was not found in this book\./);
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save to note" })).toBeNull();
  });

  it("restores a stored scope miss with the same scope-specific wording", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () => jsonResponse(200, restoredDetail),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    expect(screen.getByTestId("not-found").textContent).toMatch(
      /elsewhere in the book/i,
    );
  });
});

describe("TeachPanel thread restore (RA-10)", () => {
  it("restores the pointed-at conversation with its full cited history", async () => {
    const fetchMock = routedFetch({
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      [`GET ${READ_URL}`]: () => jsonResponse(200, restoredDetail),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);

    // Both stored turns render with their citation and their not-found callout.
    expect(await screen.findByText("It is about early computing.")).toBeTruthy();
    expect(screen.getByText("What is this about?")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Intro" }),
    ).toBeTruthy();
    expect(screen.getByText("and the weather?")).toBeTruthy();
    expect(screen.getByTestId("not-found")).toBeTruthy();

    // Ordered oldest-first: turn 0 precedes turn 1 in the DOM.
    const turns = screen.getAllByTestId("user-message");
    expect(turns.map((t) => t.textContent)).toEqual([
      "What is this about?",
      "and the weather?",
    ]);

    // The taught passage is named by the live structure, not by a stored label.
    expect(screen.getByRole("heading", { name: "Chapter 1" })).toBeTruthy();
  });

  it("offers the target picker again when the pointed-at conversation is gone", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () =>
          jsonResponse(404, { detail: "Conversation not found." }),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);

    expect(await screen.findByLabelText("Target")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("TeachPanel auth (RA-10)", () => {
  it("routes a 401 turn stream to onRequireAuth", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => new Response(null, { status: 401 }), {
          [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
        }),
      ),
    );

    const onRequireAuth = vi.fn();
    render(
      <TeachPanel sourceId="s1" csrf="csrf-xyz" onRequireAuth={onRequireAuth} />,
    );
    await startSession();
    sendMessage("a message");

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
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

/** Stream a complete, answered turn carrying `citations` and settling the stream. */
async function streamTurn(
  stream: ReturnType<typeof sseStream>,
  citations: unknown[],
) {
  await stream.push({ type: "start", messageId: "m1" });
  await stream.push({ type: "text-start", id: "t1" });
  await stream.push({ type: "text-delta", id: "t1", delta: "A lesson." });
  await stream.push({ type: "text-end", id: "t1" });
  await stream.push({ type: "data-citations", data: citations });
  await stream.push({ type: "data-answer-status", data: { status: "answered" } });
  await stream.push({ type: "finish" });
  await stream.done();
}

describe("TeachPanel save to note (RA-20/22)", () => {
  it("saves a cited taught turn as a note and confirms success", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(
      baseHandlers(() => stream.response, {
        "POST /api/sources/s1/highlights": () => jsonResponse(201, noteDetail),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    sendMessage("Explain this chapter.");
    await streamTurn(stream, [citation]);

    const saveButton = await screen.findByRole("button", {
      name: "Save to note",
    });
    await act(async () => {
      fireEvent.click(saveButton);
    });

    await waitFor(() =>
      expect(callsTo(fetchMock, "/api/sources/s1/highlights")).toHaveLength(1),
    );
    expect(await screen.findByTestId("save-note-status")).toBeTruthy();
  });

  it("offers Save to note only on the cited turn of a restored thread", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () => jsonResponse(200, restoredDetail),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    // The answered, cited turn offers the action; the not-found turn does not.
    expect(
      screen.getAllByRole("button", { name: "Save to note" }),
    ).toHaveLength(1);
  });
});

describe("TeachPanel taught passage (RA-11)", () => {
  it("shows the target in the book once on start and never per turn", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    const onShowInBook = vi.fn();
    render(
      <TeachPanel sourceId="s1" csrf="csrf-xyz" onShowInBook={onShowInBook} />,
    );
    await startSession();

    // The book is asked to show the taught anchor exactly once.
    await waitFor(() => expect(onShowInBook).toHaveBeenCalledWith("c2.xhtml"));
    expect(onShowInBook).toHaveBeenCalledTimes(1);

    // Streaming a full turn does not re-trigger the jump.
    sendMessage("Explain this chapter.");
    await streamTurn(stream, [citation]);

    await waitFor(() =>
      expect(document.body.textContent).toContain("A lesson."),
    );
    expect(onShowInBook).toHaveBeenCalledTimes(1);
  });

  it("shows a restored thread's target in the book once", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () => jsonResponse(200, restoredDetail),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    const onShowInBook = vi.fn();
    render(
      <TeachPanel sourceId="s1" csrf="csrf-xyz" onShowInBook={onShowInBook} />,
    );

    await waitFor(() => expect(onShowInBook).toHaveBeenCalledWith("c1.xhtml"));
    expect(onShowInBook).toHaveBeenCalledTimes(1);
  });
});

describe("TeachPanel include-my-notes choice (NL-04)", () => {
  it("defaults the choice off and sends it explicitly when the conversation is created", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();

    // The control reflects teaching's default (off) before any choice.
    const toggle = screen.getByRole("checkbox");
    expect((toggle as HTMLInputElement).checked).toBe(false);

    // Turning it on is carried into the conversation the next message creates.
    fireEvent.click(toggle);
    sendMessage("Explain this chapter.");

    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      include_notes: true,
    });
  });
});
