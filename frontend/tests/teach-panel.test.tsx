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
import {
  readActiveConversation,
  writeActiveConversation,
} from "../app/lib/active-conversation";

// The delete-on-failure sensor: the conversations client is real except for
// `deleteConversation`, which is replaced by a spy so a reintroduced DELETE is
// caught at the call, not just at the wire. Retry must not create a second
// conversation, so `startConversation` is wrapped the same way.
const { deleteConversationSpy, startConversationSpy } = vi.hoisted(() => ({
  deleteConversationSpy: vi.fn(),
  startConversationSpy: vi.fn(),
}));
vi.mock("../app/lib/conversations", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../app/lib/conversations")>();
  return {
    ...actual,
    deleteConversation: deleteConversationSpy,
    startConversation: (
      ...args: Parameters<typeof actual.startConversation>
    ) => {
      startConversationSpy(...args);
      return actual.startConversation(...args);
    },
  };
});

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
  // Wait out the stream throttle inside `act` so the SDK's trailing flush
  // lands and renders before the next assertion (see ask-panel's helper).
  const frame = (bytes: Uint8Array) =>
    act(async () => {
      controller.enqueue(bytes);
      await new Promise((resolve) => setTimeout(resolve, 60));
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

async function sendMessage(value: string) {
  // The input renders only once the thread is ready; with stream updates
  // throttled, restore-path state can land a beat after the fetch resolves.
  fireEvent.change(await screen.findByPlaceholderText(/send a message/i), {
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
  deleteConversationSpy.mockClear();
  startConversationSpy.mockClear();
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

    await sendMessage("Explain this chapter.");

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

    await sendMessage("first message");
    await waitFor(() => expect(streams).toHaveLength(1));
    await streamTurn(streams[0], []);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy(),
    );

    await sendMessage("second message");
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(2));

    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
  });

  it("renders the whole-book not-found state with no citations", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("unrelated nonsense");

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
    await sendMessage("a message");

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
    await sendMessage("teach me this section");

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
    await sendMessage("first try");

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
    expect(document.body.textContent).toContain("first try");
    expect(deleteConversationSpy).not.toHaveBeenCalled();
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(screen.getByTestId("failed-turn").textContent).toContain(
      "Answer generation failed",
    );
    expect(
      (screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
});

/** Every DELETE the panel issued against the taught conversation. */
function deleteCalls(fetchMock: ReturnType<typeof routedFetch>): unknown[][] {
  return fetchMock.mock.calls.filter(
    ([url, init]) =>
      url === READ_URL &&
      (init as RequestInit | undefined)?.method === "DELETE",
  );
}

describe("TeachPanel keeps the thread when a turn fails", () => {
  it("never deletes the conversation its first message created when the stream errors", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(
      baseHandlers(() => stream.response, {
        [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("a question that fails");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });
    await screen.findByRole("alert");

    expect(deleteConversationSpy).not.toHaveBeenCalled();
    expect(deleteCalls(fetchMock)).toHaveLength(0);
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(document.body.textContent).toContain("a question that fails");
  });
});

describe("TeachPanel retries a failed turn on the same conversation", () => {
  it("resubmits the same message as a new turn without creating another conversation", async () => {
    const streams = [sseStream(), sseStream()];
    let streamCalls = 0;
    const fetchMock = routedFetch(
      baseHandlers(() => streams[Math.min(streamCalls++, 1)].response),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("the same question");

    await streams[0].push({ type: "start", messageId: "m1" });
    await streams[0].push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(startConversationSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(retry);
    });

    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(2));
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[0])).toMatchObject({
      message: "the same question",
    });
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[1])).toMatchObject({
      message: "the same question",
    });
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(startConversationSpy).toHaveBeenCalledTimes(1);
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
  });

  it("disables Retry while a turn is already streaming", async () => {
    const streams = [sseStream(), sseStream()];
    let streamCalls = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        baseHandlers(() => streams[Math.min(streamCalls++, 1)].response),
      ),
    );

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("the same question");

    await streams[0].push({ type: "start", messageId: "m1" });
    await streams[0].push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect((retry as HTMLButtonElement).disabled).toBe(false);

    await act(async () => {
      fireEvent.click(retry);
    });

    await streams[1].push({ type: "start", messageId: "m2" });
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Retry" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
  });
});

describe("TeachPanel scope misses", () => {
  it("says the answer may be elsewhere in the book when the scope comes up empty", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("something from another chapter");

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

describe("TeachPanel answer phases (ANSW-01/02)", () => {
  it("shows the same search, thinking, and answer phases Ask does", async () => {
    // The dock is mode-agnostic: a taught turn waits, thinks, and answers on the
    // same unified stream, so it must read identically to an asked one.
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("Explain this chapter.");

    await waitFor(() =>
      expect(screen.queryByText(/searching the book/i)).toBeTruthy(),
    );

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "data-phase", data: { phase: "searching" } });
    await stream.push({ type: "reasoning-start", id: "r1" });
    await stream.push({
      type: "reasoning-delta",
      id: "r1",
      delta: "Start from the engine metaphor.",
    });

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "reasoning" })).toBeTruthy(),
    );
    expect(screen.queryByText(/searching the book/i)).toBeNull();
    expect(screen.getByText("Start from the engine metaphor.")).toBeTruthy();

    await stream.push({ type: "reasoning-end", id: "r1" });
    await stream.push({ type: "text-start", id: "t1" });
    await stream.push({ type: "text-delta", id: "t1", delta: "A lesson." });

    // The thinking folds away the moment the lesson starts.
    await waitFor(() =>
      expect(document.body.textContent).toContain("A lesson."),
    );
    expect(screen.queryByText("Start from the engine metaphor.")).toBeNull();
    expect(screen.getByRole("button", { name: /thought process/i })).toBeTruthy();
  });

  it("collapses a not-found turn's thinking into the not-found notice", async () => {
    // Same rule as Ask: a turn that reasoned its way to "the section does not
    // cover this" must not leave that reasoning on screen beside the retraction
    // of it. The gate is written per panel, so it is guarded per panel.
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("Explain the thing this chapter never mentions.");

    await stream.push({ type: "start", messageId: "m1" });
    await stream.push({ type: "data-phase", data: { phase: "searching" } });
    await stream.push({ type: "reasoning-start", id: "r1" });
    await stream.push({
      type: "reasoning-delta",
      id: "r1",
      delta: "This section is about something else.",
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

    const notFound = await screen.findByTestId("not-found");
    expect(notFound.textContent).toContain("not found in this book");
    expect(screen.queryByRole("region", { name: "reasoning" })).toBeNull();
    expect(screen.queryByText(/searching the book/i)).toBeNull();
    expect(
      screen.queryByText("This section is about something else."),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /thought process/i }),
    ).toBeNull();
  });

  it("shows no phase line or reasoning region for a turn that carried neither", async () => {
    const stream = sseStream();
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => stream.response)));

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession();
    await sendMessage("Explain this chapter.");
    await streamTurn(stream, [citation]);

    await waitFor(() => expect(document.body.textContent).toContain("A lesson."));
    expect(screen.queryByRole("region", { name: "reasoning" })).toBeNull();
    expect(screen.queryByText(/searching the book/i)).toBeNull();
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
    await sendMessage("a message");

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
    await sendMessage("Explain this chapter.");
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
    await sendMessage("Explain this chapter.");
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
    await sendMessage("Explain this chapter.");

    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      include_notes: true,
    });

    // From here the choice belongs to that conversation: the control reports it
    // and stops taking input rather than offering a flip that does nothing.
    await waitFor(() =>
      expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(
        true,
      ),
    );
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  });

  it("reports a restored session's choice rather than the reader's stored one", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () =>
          jsonResponse(200, { ...restoredDetail, include_notes: true }),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    // Teaching's own default is off; this thread was created with it on, and
    // the thread is what the answers obey.
    const toggle = screen.getByRole("checkbox") as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    expect(toggle.disabled).toBe(true);
  });
});
