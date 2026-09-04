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
    target_anchor: anchor,
    target_title: title,
    tutor_phase: "pump",
    hint_level: "pump",
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
    [`GET ${READ_URL}`]: () =>
      jsonResponse(200, {
        ...conversationScopedTo("c2.xhtml", "Chapter 2"),
        turns: [],
      }),
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

function tutorNetwork(extra: Record<string, Handler> = {}) {
  const streams: ReturnType<typeof sseStream>[] = [];
  const fetchMock = routedFetch(
    baseHandlers(() => {
      const stream = sseStream();
      streams.push(stream);
      return stream.response;
    }, extra),
  );
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, streams };
}

async function sendMessage(value: string) {
  // The input renders only once the thread is ready; with stream updates
  // throttled, restore-path state can land a beat after the fetch resolves.
  fireEvent.change(await screen.findByPlaceholderText(/send a message/i), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
}

/** Pick a target and click Start. Does not wait for the opening turn. */
async function clickStart(anchor = "c2.xhtml") {
  await screen.findByLabelText("Target");
  await screen.findByRole("option", { name: "Chapter 1" }, { timeout: 5000 });
  fireEvent.change(screen.getByLabelText("Target"), { target: { value: anchor } });
  fireEvent.click(screen.getByRole("button", { name: "Start session" }));
}

/** Finish the frozen opening stream and wait until the composer appears. */
async function persistOpening(
  fetchMock: ReturnType<typeof routedFetch>,
  stream: ReturnType<typeof sseStream>,
  status: "answered" | "not_found_in_source" | "failed" = "answered",
) {
  await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
  await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(1));
  expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[0])).toEqual({
    message: "(session start)",
    mode: "teach",
  });
  if (status === "failed") {
    await stream.push({ type: "start", messageId: "open" });
    await stream.push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });
  } else {
    await streamTurn(stream, [], status, "open");
  }
  await screen.findByPlaceholderText(/send a message/i, {}, { timeout: 5000 });
  if (status !== "failed") {
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Stop" })).toBeNull(),
    );
    await screen.findByRole("button", { name: "Submit" });
  }
}

/** Pick a target, Start, and persist the opening turn so the composer is ready. */
async function startSession(
  fetchMock: ReturnType<typeof routedFetch>,
  streams: ReturnType<typeof sseStream>[],
  anchor = "c2.xhtml",
) {
  await clickStart(anchor);
  await waitFor(() => expect(streams.length).toBeGreaterThan(0));
  await persistOpening(fetchMock, streams[0]);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  deleteConversationSpy.mockClear();
  startConversationSpy.mockClear();
  localStorage.clear();
});

describe("TeachPanel on the conversation surface (RA-10)", () => {
  it("scopes a new conversation to the chosen target and streams the opening teach turn", async () => {
    const { fetchMock, streams } = tutorNetwork();

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

    // Start creates the conversation immediately, then streams the frozen opening.
    await waitFor(() => expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      source_id: "s1",
      scope_anchors: ["c2.xhtml"],
      title: "Chapter 2",
      include_notes: false,
    });
    expect(
      new Headers(
        (callsTo(fetchMock, CREATE_URL)[0][1] as RequestInit).headers,
      ).get("X-CSRF-Token"),
    ).toBe("csrf-xyz");

    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(1));
    const turnPost = callsTo(fetchMock, TURN_STREAM)[0];
    expect(bodyOf(turnPost)).toEqual({
      message: "(session start)",
      mode: "teach",
    });
    expect(
      new Headers((turnPost[1] as RequestInit).headers).get("X-CSRF-Token"),
    ).toBe("csrf-xyz");

    // The opening learner bubble is never shown, and the composer waits.
    expect(screen.queryByTestId("user-message")).toBeNull();
    expect(screen.queryByText("(session start)")).toBeNull();
    expect(screen.queryByPlaceholderText(/send a message/i)).toBeNull();

    await streams[0].push({ type: "start", messageId: "open" });
    await streams[0].push({ type: "text-start", id: "t1" });
    await streams[0].push({
      type: "text-delta",
      id: "t1",
      delta: "The chapter ",
    });
    await waitFor(() =>
      expect(document.body.textContent).toContain("The chapter"),
    );
    await streams[0].push({
      type: "text-delta",
      id: "t1",
      delta: "introduces the analytical engine.",
    });
    await streams[0].push({ type: "text-end", id: "t1" });
    await streams[0].push({ type: "data-citations", data: [citation] });
    await streams[0].push({
      type: "data-answer-status",
      data: { status: "answered" },
    });
    await streams[0].push({ type: "finish" });
    await streams[0].done();

    await waitFor(() =>
      expect(document.body.textContent).toContain(
        "The chapter introduces the analytical engine.",
      ),
    );
    expect(screen.queryByText("(session start)")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 2 › Overview" }),
    ).toBeTruthy();
    expect(
      await screen.findByPlaceholderText(/send a message/i, {}, { timeout: 5000 }),
    ).toBeTruthy();
  });

  it("continues the same conversation for a second message", async () => {
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);

    await sendMessage("first message");
    await waitFor(() => expect(streams).toHaveLength(2));
    await streamTurn(streams[1], []);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy(),
    );

    await sendMessage("second message");
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(3));

    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
  });

  it("renders the whole-book not-found state with no citations", async () => {
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("unrelated nonsense");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({ type: "text-start", id: "t1" });
    await streams[1].push({ type: "text-end", id: "t1" });
    await streams[1].push({ type: "data-citations", data: [] });
    await streams[1].push({
      type: "data-answer-status",
      data: { status: "not_found_in_source" },
    });
    await streams[1].push({ type: "finish" });
    await streams[1].done();

    const notFound = await screen.findByTestId("not-found");
    expect(notFound.textContent).toContain("not found in this book");
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("shows a readable throttle message when a turn stream returns 429", async () => {
    const fetchMock = routedFetch(
      baseHandlers(() => jsonResponse(429, { detail: "Too many requests." }), {
        [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await clickStart();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
    expect(screen.getByPlaceholderText(/send a message/i)).toBeTruthy();
  });

  it("keeps the reader on the start form when the conversation cannot be created", async () => {
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
    await clickStart();

    // The failure is readable, and Start is usable again rather than leaving
    // the reader in a thread that was never created.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/still processing/i);
    expect(screen.getByLabelText("Target")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start session" })).toBeTruthy();
    expect(screen.queryByPlaceholderText(/send a message/i)).toBeNull();

    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
  });

  it("settles a mid-stream error part to a banner with partial text retained", async () => {
    const { fetchMock, streams } = tutorNetwork({
      [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
    });

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("first try");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({ type: "text-start", id: "t1" });
    await streams[1].push({ type: "text-delta", id: "t1", delta: "Partial turn" });
    await waitFor(() =>
      expect(document.body.textContent).toContain("Partial turn"),
    );
    await streams[1].push({
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
    const { fetchMock, streams } = tutorNetwork({
      [`DELETE ${READ_URL}`]: () => new Response(null, { status: 204 }),
    });

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("a question that fails");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({
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
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("the same question");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(startConversationSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(retry);
    });

    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(3));
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[0])).toEqual({
      message: "(session start)",
      mode: "teach",
    });
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[1])).toMatchObject({
      message: "the same question",
    });
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[2])).toMatchObject({
      message: "the same question",
    });
    expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1);
    expect(startConversationSpy).toHaveBeenCalledTimes(1);
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
  });

  it("disables Retry while a turn is already streaming", async () => {
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("the same question");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({
      type: "error",
      errorText: "Answer generation failed. Please try again.",
    });

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect((retry as HTMLButtonElement).disabled).toBe(false);

    await act(async () => {
      fireEvent.click(retry);
    });

    await waitFor(() => expect(streams).toHaveLength(3));
    await streams[2].push({ type: "start", messageId: "m2" });
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
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("something from another chapter");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({ type: "text-start", id: "t1" });
    await streams[1].push({ type: "text-end", id: "t1" });
    await streams[1].push({ type: "data-citations", data: [] });
    await streams[1].push({
      type: "data-answer-status",
      data: { status: "not_found_in_scope" },
    });
    await streams[1].push({ type: "finish" });
    await streams[1].done();

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
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("Explain this chapter.");
    await waitFor(() => expect(streams).toHaveLength(2));

    await waitFor(() =>
      expect(screen.queryByText(/searching the book/i)).toBeTruthy(),
    );

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({ type: "data-phase", data: { phase: "searching" } });
    await streams[1].push({ type: "reasoning-start", id: "r1" });
    await streams[1].push({
      type: "reasoning-delta",
      id: "r1",
      delta: "Start from the engine metaphor.",
    });

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "reasoning" })).toBeTruthy(),
    );
    expect(screen.queryByText(/searching the book/i)).toBeNull();
    expect(screen.getByText("Start from the engine metaphor.")).toBeTruthy();

    await streams[1].push({ type: "reasoning-end", id: "r1" });
    await streams[1].push({ type: "text-start", id: "t1" });
    await streams[1].push({ type: "text-delta", id: "t1", delta: "A lesson." });

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
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("Explain the thing this chapter never mentions.");
    await waitFor(() => expect(streams).toHaveLength(2));

    await streams[1].push({ type: "start", messageId: "m1" });
    await streams[1].push({ type: "data-phase", data: { phase: "searching" } });
    await streams[1].push({ type: "reasoning-start", id: "r1" });
    await streams[1].push({
      type: "reasoning-delta",
      id: "r1",
      delta: "This section is about something else.",
    });
    await streams[1].push({ type: "reasoning-end", id: "r1" });
    await streams[1].push({ type: "text-start", id: "t1" });
    await streams[1].push({ type: "text-end", id: "t1" });
    await streams[1].push({ type: "data-citations", data: [] });
    await streams[1].push({
      type: "data-answer-status",
      data: { status: "not_found_in_source" },
    });
    await streams[1].push({ type: "finish" });
    await streams[1].done();

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
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("Explain this chapter.");
    await waitFor(() => expect(streams).toHaveLength(2));
    await streamTurn(streams[1], [citation]);

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

  it("restores a failed turn as the question plus the error, not an empty shell", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () =>
          jsonResponse(200, {
            ...conversationScopedTo("c1.xhtml", "Chapter 1"),
            turns: [
              {
                turn_index: 0,
                message: "What is this about?",
                mode: "teach",
                answer_status: "failed",
                text: "",
                citations: [],
                evidence_count: 0,
                model: "unknown",
                created_at: "now",
              },
            ],
          }),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);

    expect(await screen.findByText("What is this about?")).toBeTruthy();
    expect(screen.getByTestId("failed-turn").textContent).toContain(
      "Answer generation failed",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByTestId("not-found")).toBeNull();
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
    await clickStart();

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

/** Stream a complete turn carrying `citations` and settling the stream. */
async function streamTurn(
  stream: ReturnType<typeof sseStream>,
  citations: unknown[],
  status: "answered" | "not_found_in_source" | "not_found_in_scope" = "answered",
  messageId = "m1",
) {
  await stream.push({ type: "start", messageId });
  await stream.push({ type: "text-start", id: "t1" });
  await stream.push({
    type: "text-delta",
    id: "t1",
    delta: status === "answered" ? "A lesson." : "",
  });
  await stream.push({ type: "text-end", id: "t1" });
  await stream.push({ type: "data-citations", data: citations });
  await stream.push({ type: "data-answer-status", data: { status } });
  await stream.push({ type: "finish" });
  await stream.done();
}

describe("TeachPanel save to note (RA-20/22)", () => {
  it("saves a cited taught turn as a note and confirms success", async () => {
    const { fetchMock, streams } = tutorNetwork({
      "POST /api/sources/s1/highlights": () => jsonResponse(201, noteDetail),
    });

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);
    await sendMessage("Explain this chapter.");
    await waitFor(() => expect(streams).toHaveLength(2));
    await streamTurn(streams[1], [citation]);

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
    const { fetchMock, streams } = tutorNetwork();

    const onShowInBook = vi.fn();
    render(
      <TeachPanel sourceId="s1" csrf="csrf-xyz" onShowInBook={onShowInBook} />,
    );
    await startSession(fetchMock, streams);

    // The book is asked to show the taught anchor exactly once.
    await waitFor(() => expect(onShowInBook).toHaveBeenCalledWith("c2.xhtml"));
    expect(onShowInBook).toHaveBeenCalledTimes(1);

    // Streaming a full turn does not re-trigger the jump.
    await sendMessage("Explain this chapter.");
    await waitFor(() => expect(streams).toHaveLength(2));
    await streamTurn(streams[1], [citation]);

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
  it("sends include_notes false on Tutor Start and locks the control", async () => {
    const { fetchMock, streams } = tutorNetwork();

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);

    expect(bodyOf(callsTo(fetchMock, CREATE_URL)[0])).toMatchObject({
      include_notes: false,
    });

    const toggle = screen.getByRole("checkbox") as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(toggle.disabled).toBe(true);
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

describe("Tutor Start speaks first (TUTOR-08/13/14/29/30)", () => {
  it("names Answer and Tutor as distinct modes on the empty Tutor start form", async () => {
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => sseStream().response)));
    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByLabelText("Target");
    expect(document.body.textContent).toMatch(/Tutor/);
    expect(document.body.textContent).toMatch(/Answer/);
  });

  it("defaults the section picker to the chapter currently on screen", async () => {
    vi.stubGlobal("fetch", routedFetch(baseHandlers(() => sseStream().response)));
    render(
      <TeachPanel sourceId="s1" csrf="csrf-xyz" currentAnchor="c2.xhtml" />,
    );
    const target = await screen.findByLabelText("Target");
    expect((target as HTMLSelectElement).value).toBe("c2.xhtml");
    expect(screen.getByRole("button", { name: "Start session" })).toBeTruthy();
  });

  it("shows the composer after a not-found opening turn persists", async () => {
    const { fetchMock, streams } = tutorNetwork();
    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await clickStart();
    await waitFor(() => expect(streams.length).toBeGreaterThan(0));
    expect(screen.queryByPlaceholderText(/send a message/i)).toBeNull();
    await persistOpening(fetchMock, streams[0], "not_found_in_source");
    expect(screen.getByPlaceholderText(/send a message/i)).toBeTruthy();
    expect(screen.queryByText("(session start)")).toBeNull();
  });

  it("shows the composer after a failed opening turn persists, without the sentinel bubble", async () => {
    const { fetchMock, streams } = tutorNetwork();
    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await clickStart();
    await waitFor(() => expect(streams.length).toBeGreaterThan(0));
    await persistOpening(fetchMock, streams[0], "failed");
    expect(screen.getByPlaceholderText(/send a message/i)).toBeTruthy();
    expect(screen.queryByText("(session start)")).toBeNull();
    expect(screen.queryByTestId("user-message")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("Tutor chips and closed-session handoff (TUTOR-18/19/33)", () => {
  it("posts Just explain this. as the exact teach message", async () => {
    const { fetchMock, streams } = tutorNetwork();
    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);

    fireEvent.click(
      screen.getByRole("button", { name: "Just explain this." }),
    );
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(2));
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[1])).toEqual({
      message: "Just explain this.",
      mode: "teach",
    });
    await streamTurn(streams[1], []);
  });

  it("posts I don't know. as the exact teach message", async () => {
    const { fetchMock, streams } = tutorNetwork();
    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await startSession(fetchMock, streams);

    fireEvent.click(screen.getByRole("button", { name: "I don't know." }));
    await waitFor(() => expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(2));
    expect(bodyOf(callsTo(fetchMock, TURN_STREAM)[1])).toEqual({
      message: "I don't know.",
      mode: "teach",
    });
    await streamTurn(streams[1], []);
  });

  it("hides the composer when the session is closed and Ask about this does not post a turn", async () => {
    const fetchMock = routedFetch({
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      [`GET ${READ_URL}`]: () =>
        jsonResponse(200, {
          ...restoredDetail,
          tutor_phase: "close",
          target_title: "Chapter 1",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "teach", "conv2");

    const onAskAboutThis = vi.fn();
    render(
      <TeachPanel
        sourceId="s1"
        csrf="csrf-xyz"
        onAskAboutThis={onAskAboutThis}
      />,
    );
    await screen.findByText("It is about early computing.");

    expect(screen.queryByPlaceholderText(/send a message/i)).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Just explain this." }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();

    const turnCount = callsTo(fetchMock, TURN_STREAM).length;
    fireEvent.click(screen.getByRole("button", { name: "Ask about this" }));
    expect(onAskAboutThis).toHaveBeenCalledTimes(1);
    expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(turnCount);
  });
});

describe("Tutor review card offer (TUTOR-34/41)", () => {
  const TUTOR_CARD_URL = "/api/conversations/conv2/tutor-card";
  const checkText = "It argues that location anchors must stay stable.";

  function closedConversation() {
    return {
      ...restoredDetail,
      tutor_phase: "close",
      target_title: "Chapter 1",
      tutor_check_text: checkText,
    };
  }

  it("offers exactly one card with the frozen question and the check text", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        [`GET ${READ_URL}`]: () => jsonResponse(200, closedConversation()),
      }),
    );
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    const offer = screen.getByRole("article", { name: "review card offer" });
    expect(offer.textContent).toContain(
      'In your own words, what is "Chapter 1" arguing?',
    );
    expect(offer.textContent).toContain(checkText);
    expect(screen.getAllByRole("article", { name: "review card offer" })).toHaveLength(
      1,
    );
  });

  it("Accept posts to the tutor-card route and does not suggest cards", async () => {
    const fetchMock = routedFetch({
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      [`GET ${READ_URL}`]: () => jsonResponse(200, closedConversation()),
      [`POST ${TUTOR_CARD_URL}`]: () => jsonResponse(201, { id: "q1" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, TUTOR_CARD_URL)).toHaveLength(1),
    );
    const accept = callsTo(fetchMock, TUTOR_CARD_URL)[0];
    expect((accept[1] as RequestInit).method).toBe("POST");
    expect(
      new Headers((accept[1] as RequestInit).headers).get("X-CSRF-Token"),
    ).toBe("csrf-xyz");
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("/cards/suggestions"),
      ),
    ).toBe(false);
    await waitFor(() =>
      expect(
        screen.queryByRole("article", { name: "review card offer" }),
      ).toBeNull(),
    );
  });

  it("Dismiss hides the offer and writes no quiz row", async () => {
    const fetchMock = routedFetch({
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      [`GET ${READ_URL}`]: () => jsonResponse(200, closedConversation()),
    });
    vi.stubGlobal("fetch", fetchMock);
    writeActiveConversation("s1", "teach", "conv2");

    render(<TeachPanel sourceId="s1" csrf="csrf-xyz" />);
    await screen.findByText("It is about early computing.");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("article", { name: "review card offer" })).toBeNull();
    expect(callsTo(fetchMock, TUTOR_CARD_URL)).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Ask about this" })).toBeTruthy();
  });
});
