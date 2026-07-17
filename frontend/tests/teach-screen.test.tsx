// @vitest-environment jsdom

/**
 * D4 gate (component) — the teach screen builds a target picker from the
 * structure endpoint and a resume list with turn counts (FE-11); starting a
 * session streams a cited turn's deltas progressively and posts `{message}` to
 * the turns stream (FE-12); resuming seeds the conversation from persisted turns
 * so prior turns render with their citations (FE-12); and a throttle (429),
 * mid-stream error, or not-found settle to the same readable state contract as
 * Ask (FE-13).
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

import { TeachScreen } from "../app/components/teach-screen";

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

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

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

const chapter2Session = {
  id: "sess1",
  source_id: "s1",
  target: { anchor: "c2.xhtml", section_path: ["Chapter 2"], title: "Chapter 2" },
  created_at: "now",
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

const summary = {
  id: "sess1",
  target: { anchor: "c1.xhtml", section_path: ["Chapter 1"], title: "Chapter 1" },
  created_at: "now",
  turn_count: 2,
};

/** A resumed session's stored, ordered, cited history. */
const resumedDetail = {
  id: "sess1",
  source_id: "s1",
  target: { anchor: "c1.xhtml", section_path: ["Chapter 1"], title: "Chapter 1" },
  created_at: "now",
  turns: [
    {
      turn_index: 0,
      message: "What is this about?",
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
      answer_status: "not_found_in_source",
      text: "",
      citations: [],
      evidence_count: 0,
      model: "local-extractive",
      created_at: "now",
    },
  ],
};

const TURN_STREAM = "/api/teaching-sessions/sess1/turns/stream";

function baseHandlers(): Record<string, Handler> {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
    "GET /api/sources/s1/teaching-sessions": () => jsonResponse(200, []),
  };
}

function sendMessage(value: string) {
  fireEvent.change(screen.getByPlaceholderText(/send a message/i), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TeachScreen start + stream (D4)", () => {
  it("builds the target picker, starts a session, and streams a cited turn progressively", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch({
      ...baseHandlers(),
      "POST /api/teaching-sessions": () => jsonResponse(201, chapter2Session),
      [`POST ${TURN_STREAM}`]: () => stream.response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachScreen sourceId="s1" />);

    // FE-11: every flattened section (incl. the nested one as a breadcrumb) is offered.
    await screen.findByLabelText("Target");
    expect(screen.getByRole("option", { name: "Chapter 1" })).toBeTruthy();
    expect(
      screen.getByRole("option", { name: "Chapter 1 › Section 1.1" }),
    ).toBeTruthy();
    expect(screen.getByRole("option", { name: "Chapter 2" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "c2.xhtml" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    // The start POST carried the chosen target anchor.
    await screen.findByPlaceholderText(/send a message/i);
    const startPost = fetchMock.mock.calls.find(
      ([url]) => url === "/api/teaching-sessions",
    )!;
    expect(JSON.parse((startPost[1] as RequestInit).body as string)).toEqual({
      source_id: "s1",
      target_anchor: "c2.xhtml",
    });

    sendMessage("Explain this chapter.");

    // FE-12: the turn POSTs {message} with the CSRF header to the turns stream.
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url === TURN_STREAM)).toBe(
        true,
      ),
    );
    const turnPost = fetchMock.mock.calls.find(([url]) => url === TURN_STREAM)!;
    expect(JSON.parse((turnPost[1] as RequestInit).body as string)).toEqual({
      message: "Explain this chapter.",
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

  it("renders the not-found state with no citations on not_found_in_source", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        ...baseHandlers(),
        "POST /api/teaching-sessions": () => jsonResponse(201, chapter2Session),
        [`POST ${TURN_STREAM}`]: () => stream.response,
      }),
    );

    render(<TeachScreen sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByPlaceholderText(/send a message/i);
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
    expect(notFound.textContent).toContain("not found in this target");
    expect(screen.queryByRole("button", { name: /^Citation:/ })).toBeNull();
  });

  it("shows a readable throttle message when a turn stream returns 429", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        ...baseHandlers(),
        "POST /api/teaching-sessions": () => jsonResponse(201, chapter2Session),
        [`POST ${TURN_STREAM}`]: () =>
          jsonResponse(429, { detail: "Too many requests." }),
      }),
    );

    render(<TeachScreen sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByPlaceholderText(/send a message/i);
    sendMessage("a message");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too many requests/i);
  });

  it("settles a mid-stream error part to a banner with partial text retained", async () => {
    const stream = sseStream();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        ...baseHandlers(),
        "POST /api/teaching-sessions": () => jsonResponse(201, chapter2Session),
        [`POST ${TURN_STREAM}`]: () => stream.response,
      }),
    );

    render(<TeachScreen sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByPlaceholderText(/send a message/i);
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

describe("TeachScreen resume (D4)", () => {
  it("lists previous sessions with turn counts and resumes full cited history", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
        "GET /api/sources/s1/teaching-sessions": () =>
          jsonResponse(200, [summary]),
        "GET /api/teaching-sessions/sess1": () =>
          jsonResponse(200, resumedDetail),
      }),
    );

    render(<TeachScreen sourceId="s1" />);

    // FE-11: the resume list shows the session with its turn count.
    await screen.findByText("Previous sessions");
    expect(screen.getByText(/2 turns/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    // FE-12: seeded history renders both stored turns with their citation and callout.
    expect(await screen.findByText("It is about early computing.")).toBeTruthy();
    expect(screen.getByText("What is this about?")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Intro" }),
    ).toBeTruthy();

    expect(screen.getByText("and the weather?")).toBeTruthy();
    expect(screen.getByTestId("not-found").textContent).toContain(
      "not found in this target",
    );

    // Ordered oldest-first: turn 0 precedes turn 1 in the DOM.
    const turns = screen.getAllByTestId("user-message");
    expect(turns.map((t) => t.textContent)).toEqual([
      "What is this about?",
      "and the weather?",
    ]);
  });
});

describe("TeachScreen auth (D4)", () => {
  it("does a UX-only redirect and shows the signed-out state when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<TeachScreen sourceId="s1" onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});
