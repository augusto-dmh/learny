// @vitest-environment jsdom

/**
 * B1 (component) — the Ask panel is the ask screen's streaming chat ported into
 * the reader side panel. It keeps parity with the old screen: it POSTs
 * `{question}` with the CSRF header to the stream URL (RA-07), renders text deltas
 * progressively, renders the terminal citations or the explicit not-found state,
 * settles a mid-stream `error` part or a non-OK start (429) to a readable banner
 * with partial text retained and the input re-enabled, swaps submit for stop while
 * streaming, never submits empty input, and routes a 401 to `onRequireAuth`.
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

describe("AskPanel streaming (RA-07)", () => {
  it("POSTs {question} with the CSRF header, streams deltas before finish, and renders citations", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    ask("Who wrote the first algorithm?");

    // The request went to the stream URL with the exact body and CSRF header.
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

  it("renders the not-found state with no citations on not_found_in_source", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${STREAM_URL}`]: () => stream.response }),
    );

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
    expect(notFound.textContent).toContain("not found in this source");
    // No citation chips are rendered for a not-found answer.
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("settles a mid-stream error part to a banner, retaining partial text and re-enabling input", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${STREAM_URL}`]: () => stream.response }),
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

  it("shows a readable throttle message when the stream start returns 429", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${STREAM_URL}`]: () =>
          jsonResponse(429, { detail: "Too many requests." }),
      }),
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

  it("swaps submit for a stop control while streaming and issues only one request", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
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
      [`POST ${STREAM_URL}`]: () => sseStream().response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    // No stream request is issued for an empty question.
    await Promise.resolve();
    expect(
      fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
    ).toBe(false);
  });
});

describe("AskPanel auth (RA-07)", () => {
  it("routes a 401 stream start to onRequireAuth without a banner", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${STREAM_URL}`]: () => new Response(null, { status: 401 }),
      }),
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
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    // The empty state offers a fixed set of suggested prompts.
    const suggestions = screen.getByLabelText("suggested prompts");
    const prompts = Array.from(suggestions.querySelectorAll("button"));
    expect(prompts).toHaveLength(3);
    const chosen = prompts[0].textContent!;

    fireEvent.click(prompts[0]);

    // Clicking a prompt submits it verbatim as a question.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => url === STREAM_URL)!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      question: chosen,
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
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${STREAM_URL}`]: () => stream.response }),
    );

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
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, noteDetail),
    });
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
      expect(
        fetchMock.mock.calls.some(([url]) => url === HIGHLIGHTS_URL),
      ).toBe(true),
    );
    expect(await screen.findByTestId("save-note-status")).toBeTruthy();
  });

  it("shows an inline error and no confirmation when saving fails", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${STREAM_URL}`]: () => stream.response,
        [`POST ${HIGHLIGHTS_URL}`]: () =>
          jsonResponse(500, { detail: "boom" }),
      }),
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
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${STREAM_URL}`]: () => stream.response }),
    );

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
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${STREAM_URL}`]: () => stream.response }),
    );

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
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
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
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => url === STREAM_URL)!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      question: 'Explain this passage from the book:\n\n"the selected sentence"',
    });
    // The request is consumed exactly once, so it never re-submits.
    expect(onPendingConsumed).toHaveBeenCalledTimes(1);
    expect(
      fetchMock.mock.calls.filter(([url]) => url === STREAM_URL),
    ).toHaveLength(1);
  });

  it("attaches the quote as context and submits it with the typed question", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      [`POST ${STREAM_URL}`]: () => stream.response,
    });
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
    expect(
      fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
    ).toBe(false);

    // The typed question rides along with the attached quote in the fixed shape.
    ask("What does this mean?");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === STREAM_URL),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => url === STREAM_URL)!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      question:
        'Regarding this passage:\n\n"a quoted passage"\n\nWhat does this mean?',
    });
  });
});
