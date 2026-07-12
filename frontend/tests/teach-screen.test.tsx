// @vitest-environment jsdom

/**
 * E2 gate (component) — the teach view builds a target picker from the structure
 * endpoint, starts a session on the chosen target, sends a message through the
 * same-origin proxy and renders the cited response (section-path breadcrumb +
 * snippet), renders the explicit not-found callout, resumes a previous session's
 * full history from the GET endpoint, and surfaces readable 409/422/429/502
 * errors that leave the composer usable (TEACH-22).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeachPanel } from "../app/components/TeachPanel";

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

const chapter1Session = {
  id: "sess1",
  source_id: "s1",
  target: { anchor: "c1.xhtml", section_path: ["Chapter 1"], title: "Chapter 1" },
  created_at: "now",
};

const answeredTurn = {
  turn_index: 0,
  message: "Explain this chapter.",
  answer_status: "answered",
  text: "The chapter introduces the analytical engine.",
  citations: [
    {
      chunk_id: "c1",
      source_id: "s1",
      section_path: ["Chapter 2", "Overview"],
      anchor: "c2.xhtml#overview",
      page_span: null,
      snippet: "a note on the analytical engine",
      score: 0.02,
    },
  ],
  evidence_count: 8,
  model: "local-extractive",
  created_at: "now",
};

const notFoundTurn = {
  turn_index: 0,
  message: "unrelated nonsense",
  answer_status: "not_found_in_source",
  text: "",
  citations: [],
  evidence_count: 0,
  model: "local-extractive",
  created_at: "now",
};

const summary = {
  id: "sess1",
  target: { anchor: "c1.xhtml", section_path: ["Chapter 1"], title: "Chapter 1" },
  created_at: "now",
  turn_count: 2,
};

/** A resumed session's stored, ordered, cited history. */
const resumedDetail = {
  ...chapter1Session,
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

/** Base handlers: authed, with the source's structure and an empty session list. */
function baseHandlers(): Record<string, Handler> {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
    "GET /api/sources/s1/teaching-sessions": () => jsonResponse(200, []),
  };
}

function sendMessage(value: string) {
  fireEvent.change(screen.getByLabelText("Message"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TeachPanel start + turn flow (E2)", () => {
  it("picks a target, starts a session, and renders the cited response to a message", async () => {
    const fetchMock = routedFetch({
      ...baseHandlers(),
      "POST /api/teaching-sessions": () => jsonResponse(201, chapter2Session),
      "POST /api/teaching-sessions/sess1/turns": () =>
        jsonResponse(201, answeredTurn),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" />);

    // The picker is built from the structure endpoint: every flattened section
    // is offered, including the nested one as a breadcrumb.
    await screen.findByLabelText("Target");
    expect(screen.getByRole("option", { name: "Chapter 1" })).toBeTruthy();
    expect(
      screen.getByRole("option", { name: "Chapter 1 › Section 1.1" }),
    ).toBeTruthy();
    expect(screen.getByRole("option", { name: "Chapter 2" })).toBeTruthy();

    // Pick Chapter 2 and start the session.
    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "c2.xhtml" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    // The start POST carried the chosen target anchor.
    await screen.findByLabelText("Message");
    const startPost = fetchMock.mock.calls.find(
      ([url]) => url === "/api/teaching-sessions",
    );
    expect(JSON.parse((startPost?.[1] as RequestInit).body as string)).toEqual({
      source_id: "s1",
      target_anchor: "c2.xhtml",
    });

    // Send a message; the cited response renders with prose, section-path
    // breadcrumb, and snippet.
    sendMessage("Explain this chapter.");
    expect(
      await screen.findByText("The chapter introduces the analytical engine."),
    ).toBeTruthy();
    expect(screen.getByText("Explain this chapter.")).toBeTruthy();
    expect(screen.getByText("Chapter 2 › Overview")).toBeTruthy();
    expect(screen.getByText("a note on the analytical engine")).toBeTruthy();
  });

  it("renders an explicit not-found callout and no citations on not_found_in_source", async () => {
    const fetchMock = routedFetch({
      ...baseHandlers(),
      "POST /api/teaching-sessions": () => jsonResponse(201, chapter1Session),
      "POST /api/teaching-sessions/sess1/turns": () =>
        jsonResponse(201, notFoundTurn),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    await screen.findByLabelText("Message");
    sendMessage("unrelated nonsense");

    const message = await screen.findByTestId("not-found");
    expect(message.textContent).toContain("not found in this target");
    expect(screen.queryByTestId("answer")).toBeNull();
  });

  it("keeps the composer usable after a readable error, then succeeds", async () => {
    let posts = 0;
    const fetchMock = routedFetch({
      ...baseHandlers(),
      "POST /api/teaching-sessions": () => jsonResponse(201, chapter1Session),
      "POST /api/teaching-sessions/sess1/turns": () => {
        posts += 1;
        return posts === 1
          ? jsonResponse(409, {
              detail: "Target no longer exists; start a new session.",
            })
          : jsonResponse(201, answeredTurn);
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByLabelText("Message");

    // First send fails: the backend detail renders as a readable error.
    sendMessage("first try");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Target no longer exists; start a new session.",
    );
    expect(screen.queryByTestId("answer")).toBeNull();

    // The composer is still usable — a second send succeeds and clears the error.
    sendMessage("second try");
    expect(
      await screen.findByText("The chapter introduces the analytical engine."),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(posts).toBe(2);
  });

  it.each([
    [422, "Message must be at most 2000 characters."],
    [429, "Too many requests. Try again shortly."],
    [502, "Generation failed. Please try again."],
  ])(
    "surfaces a readable error on a %i turn response",
    async (status, detail) => {
      const fetchMock = routedFetch({
        ...baseHandlers(),
        "POST /api/teaching-sessions": () => jsonResponse(201, chapter1Session),
        "POST /api/teaching-sessions/sess1/turns": () =>
          jsonResponse(status as number, { detail }),
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<TeachPanel sourceId="s1" />);
      await screen.findByLabelText("Target");
      fireEvent.click(screen.getByRole("button", { name: "Start session" }));
      await screen.findByLabelText("Message");

      sendMessage("a message");
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toBe(detail);
      expect(screen.queryByTestId("answer")).toBeNull();
      // The composer remains mounted and usable for a retry.
      expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
    },
  );

  it("surfaces a readable error when starting the session is rejected", async () => {
    const fetchMock = routedFetch({
      ...baseHandlers(),
      "POST /api/teaching-sessions": () =>
        jsonResponse(409, { detail: "Source is not ready." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" />);
    await screen.findByLabelText("Target");
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Source is not ready.");
    // Stayed on the picker view; no conversation composer appeared.
    expect(screen.queryByLabelText("Message")).toBeNull();
    expect(screen.getByRole("button", { name: "Start session" })).toBeTruthy();
  });
});

describe("TeachPanel resume (E2)", () => {
  it("renders a previous session's full ordered history via the GET endpoint", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources/s1/structure": () => jsonResponse(200, structure),
      "GET /api/sources/s1/teaching-sessions": () =>
        jsonResponse(200, [summary]),
      "GET /api/teaching-sessions/sess1": () => jsonResponse(200, resumedDetail),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeachPanel sourceId="s1" />);

    // The previous-sessions list offers a resume control.
    await screen.findByText("Previous sessions");
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    // Both stored turns render in order: the answered one with its citation and
    // the not-found one as an explicit callout.
    expect(await screen.findByText("It is about early computing.")).toBeTruthy();
    expect(screen.getByText("What is this about?")).toBeTruthy();
    expect(screen.getByText("Chapter 1 › Intro")).toBeTruthy();
    expect(screen.getByText("early computing history")).toBeTruthy();

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

describe("TeachPanel auth (E2)", () => {
  it("does a UX-only redirect and shows the signed-out state when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<TeachPanel sourceId="s1" onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});
