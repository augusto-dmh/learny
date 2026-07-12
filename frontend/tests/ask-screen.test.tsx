// @vitest-environment jsdom

/**
 * D2 gate (component) — the ask view submits a question through the same-origin
 * proxy and renders the grounded answer with its citations, the explicit
 * not-found message, or a readable error that leaves the form usable
 * (QA-18..QA-20); the sources list links ready rows to their ask view (QA-18).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskPanel } from "../app/components/AskPanel";
import { SourcesPanel } from "../app/components/SourcesPanel";

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

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

const answered = {
  answer_status: "answered",
  answer: "Ada Lovelace wrote the first algorithm.",
  citations: [
    {
      chunk_id: "c1",
      source_id: "s1",
      section_path: ["Chapter 1", "Core Idea"],
      anchor: "chapter-1.xhtml#core-idea",
      page_span: null,
      snippet: "the first algorithm ever written",
      score: 0.03,
    },
    {
      chunk_id: "c2",
      source_id: "s1",
      section_path: ["Chapter 2"],
      anchor: "chapter-2.xhtml",
      page_span: null,
      snippet: "a note on the analytical engine",
      score: 0.01,
    },
  ],
  retrieval: { strategy: "hybrid", evidence_count: 8 },
  model: "local-extractive",
};

const notFound = {
  answer_status: "not_found_in_source",
  answer: "",
  citations: [],
  retrieval: { strategy: "hybrid", evidence_count: 0 },
  model: "local-extractive",
};

function sourceRow(id: string, title: string, status: string) {
  return {
    id,
    title,
    filename: `${id}.epub`,
    byte_size: 3,
    content_type: "application/epub+zip",
    status,
    created_at: "now",
  };
}

function askQuestionText(value: string) {
  fireEvent.change(screen.getByLabelText("Question"), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AskPanel (D2)", () => {
  it("renders the answer text and each citation's section path and snippet", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "POST /api/sources/s1/questions": () => jsonResponse(200, answered),
      }),
    );

    render(<AskPanel sourceId="s1" />);
    await screen.findByLabelText("Question");

    askQuestionText("Who wrote the first algorithm?");

    // Answer prose renders.
    expect(
      await screen.findByText("Ada Lovelace wrote the first algorithm."),
    ).toBeTruthy();
    // Each citation renders its section path (joined by " › ") and snippet.
    expect(screen.getByText("Chapter 1 › Core Idea")).toBeTruthy();
    expect(screen.getByText("the first algorithm ever written")).toBeTruthy();
    expect(screen.getByText("Chapter 2")).toBeTruthy();
    expect(screen.getByText("a note on the analytical engine")).toBeTruthy();
  });

  it("renders an explicit not-found message and no citations on not_found_in_source", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "POST /api/sources/s1/questions": () => jsonResponse(200, notFound),
      }),
    );

    render(<AskPanel sourceId="s1" />);
    await screen.findByLabelText("Question");

    askQuestionText("nonsense token");

    const message = await screen.findByTestId("not-found");
    expect(message.textContent).toContain("not found in this source");
    // No answer block and therefore no citation list rendered.
    expect(screen.queryByTestId("answer")).toBeNull();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  it("renders a readable error and keeps the form usable to resubmit", async () => {
    let posts = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "POST /api/sources/s1/questions": () => {
          posts += 1;
          return posts === 1
            ? jsonResponse(409, {
                detail: "Source is not ready for questions.",
              })
            : jsonResponse(200, answered);
        },
      }),
    );

    render(<AskPanel sourceId="s1" />);
    await screen.findByLabelText("Question");

    // First ask fails: the backend detail renders as a readable error.
    askQuestionText("first try");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Source is not ready for questions.");
    expect(screen.queryByTestId("answer")).toBeNull();

    // The form is still usable — a second ask succeeds and clears the error.
    askQuestionText("second try");
    expect(
      await screen.findByText("Ada Lovelace wrote the first algorithm."),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(posts).toBe(2);
  });

  it("does a UX-only redirect and shows the signed-out state when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<AskPanel sourceId="s1" onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});

describe("SourcesPanel ask link (D2)", () => {
  it("links only ready rows to their ask view", async () => {
    const mixed = [
      sourceRow("s-up", "Uploaded Book", "uploaded"),
      sourceRow("s-proc", "Processing Book", "processing"),
      sourceRow("s-ready", "Ready Book", "ready"),
      sourceRow("s-fail", "Failed Book", "failed"),
    ];
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, mixed),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    // Exactly one Ask link — on the sole ready row, pointing at its ask view.
    const askLinks = screen.getAllByRole("link", { name: "Ask" });
    expect(askLinks).toHaveLength(1);
    expect(askLinks[0].getAttribute("href")).toBe("/sources/s-ready/ask");
    const readyLi = screen.getByTestId("status-s-ready").closest("li");
    expect(within(readyLi!).getByRole("link", { name: "Ask" })).toBeTruthy();

    // Non-ready rows offer no ask link.
    for (const id of ["s-up", "s-proc", "s-fail"]) {
      const li = screen.getByTestId(`status-${id}`).closest("li");
      expect(within(li!).queryByRole("link", { name: "Ask" })).toBeNull();
    }
  });
});
