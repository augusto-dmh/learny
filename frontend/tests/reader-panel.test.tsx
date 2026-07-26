// @vitest-environment jsdom

/**
 * A (RA-01/02/03) — the reader side-panel shell hosts an Ask | Teach segmented
 * control and a close control. It renders the body for the active mode, marks the
 * active tab as selected, and reports mode switches and close through its
 * callbacks (the parent turns those into URL changes). Open state and mode are
 * driven entirely by props derived from `?panel=`, so the shell itself is a pure
 * function of `mode`.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReaderPanel } from "../app/components/reader-panel";
import { readActiveConversation } from "../app/lib/active-conversation";

// The shell test covers tabs, close, and which mode's body renders — not the
// chat internals (unit-tested in ask-panel.test.tsx, which pull in AI-Elements).
// Stub the ported bodies to their markers so the shell stays a pure unit test;
// each stub also surfaces its `onShowInBook` prop through a button so the shell's
// forwarding of the citation-jump callback to BOTH modes can be driven by a click.
type StubProps = {
  revision?: number;
  onShowInBook?: (anchor: string) => void;
};
vi.mock("../app/components/ask-panel", () => ({
  AskPanel: ({ revision, onShowInBook }: StubProps) => (
    <div data-testid="ask-panel-body" data-revision={revision}>
      <button type="button" onClick={() => onShowInBook?.("ask#anchor")}>
        ask-show-in-book
      </button>
    </div>
  ),
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: ({ revision, onShowInBook }: StubProps) => (
    <div data-testid="teach-panel-body" data-revision={revision}>
      <button type="button" onClick={() => onShowInBook?.("teach#anchor")}>
        teach-show-in-book
      </button>
    </div>
  ),
}));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A conversation summary row as the list endpoint returns it. */
function summary(
  id: string,
  title: string,
  turnCount: number,
  scopeAnchors: string[] = [],
) {
  return {
    id,
    source_id: "s1",
    source_title: "A Book",
    title,
    scope_anchors: scopeAnchors,
    include_notes: false,
    turn_count: turnCount,
    created_at: "now",
    updated_at: "now",
  };
}

/** The dock always loads the book's conversations; default to none. */
function stubList(rows: unknown[] = []) {
  const fetchMock = vi.fn(async () => jsonResponse(200, rows));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** One stored turn — the only place a conversation records how it is answered. */
function turn(mode: "answer" | "teach") {
  return {
    turn_index: 0,
    message: "a message",
    mode,
    answer_status: "answered",
    text: "a reply",
    citations: [],
    evidence_count: 2,
    model: "local-extractive",
    created_at: "now",
  };
}

/**
 * The list plus each conversation's stored turns, so a resume reads the mode the
 * server actually recorded rather than anything the row's shape suggests.
 */
function stubServer(
  rows: ReturnType<typeof summary>[],
  turnsById: Record<string, ReturnType<typeof turn>[]> = {},
) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith("/api/conversations?")) {
      return jsonResponse(200, rows);
    }
    const id = url.slice("/api/conversations/".length);
    const row = rows.find((candidate) => candidate.id === id);
    if (!row) {
      throw new Error(`unexpected fetch: ${url}`);
    }
    return jsonResponse(200, { ...row, turns: turnsById[id] ?? [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  stubList();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("ReaderPanel shell (RA-01/02/03)", () => {
  it("offers exactly the Ask and Teach modes plus a close control", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByRole("tab", { name: "Ask" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Teach" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Close panel" })).toBeTruthy();
  });

  it("renders the ask body and selects the ask tab in ask mode (RA-01)", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Ask" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      screen.getByRole("tab", { name: "Teach" }).getAttribute("aria-selected"),
    ).toBe("false");
  });

  it("renders the teach body and selects the teach tab in teach mode (RA-02)", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="teach" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("ask-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Teach" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("reports the chosen mode when a tab is clicked (RA-03)", () => {
    const onModeChange = vi.fn();
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={onModeChange} onClose={() => {}} />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));
    expect(onModeChange).toHaveBeenCalledWith("teach");
  });

  it("reports a close request when the close control is clicked (RA-03)", () => {
    const onClose = vi.fn();
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={onClose} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("forwards the show-in-book callback to the active mode body (RA-13/14)", () => {
    const onShowInBook = vi.fn();

    // Ask mode: the ask body's jump reaches the shell's callback with its anchor.
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        mode="ask"
        onModeChange={() => {}}
        onClose={() => {}}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "ask-show-in-book" }));
    expect(onShowInBook).toHaveBeenCalledWith("ask#anchor");

    // Teach mode: the teach body's jump reaches the same callback — both wired.
    rerender(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        mode="teach"
        onModeChange={() => {}}
        onClose={() => {}}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "teach-show-in-book" }));
    expect(onShowInBook).toHaveBeenCalledWith("teach#anchor");
  });
});

describe("ReaderPanel conversation list", () => {
  function renderPanel(
    mode: "ask" | "teach" = "ask",
    onModeChange: (mode: "ask" | "teach") => void = () => {},
  ) {
    return render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        mode={mode}
        onModeChange={onModeChange}
        onClose={() => {}}
      />,
    );
  }

  it("lists this book's conversations with their titles and turn counts", async () => {
    const fetchMock = stubList([
      summary("conv2", "Chapter 2", 3, ["c2.xhtml"]),
      summary("conv1", "Ada Lovelace", 1),
    ]);
    renderPanel();

    // The list is narrowed to this book and shows every conversation it holds.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Resume Chapter 2" })).toBeTruthy(),
    );
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain("source_id=s1");

    // Order is the server's — newest activity first — and each row carries its
    // turn count.
    const rows = screen.getAllByRole("button", { name: /^Resume / });
    expect(rows.map((row) => row.textContent?.trim())).toEqual([
      "Chapter 2 (3 turns)",
      "Ada Lovelace (1 turns)",
    ]);
  });

  it("shows one list holding both a scoped and a whole-book conversation", async () => {
    stubList([
      summary("conv2", "Chapter 2", 3, ["c2.xhtml"]),
      summary("conv1", "Ada Lovelace", 1),
    ]);
    renderPanel("teach");

    // A conversation started by teaching and one started by asking sit in the
    // same list, in whichever mode the dock is showing.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /^Resume / })).toHaveLength(2),
    );
  });

  it("says so when a book has no conversations yet", async () => {
    stubList([]);
    renderPanel();

    expect(await screen.findByText("No conversations yet.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reaches an older conversation than one page holds", async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) =>
      summary(`c${index}`, `Thread ${index}`, 1),
    );
    const secondPage = [summary("c20", "The oldest thread", 1)];
    const fetchMock = vi.fn(async (url: string) =>
      jsonResponse(200, url.includes("offset=20") ? secondPage : firstPage),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();

    // The dock asks for one bounded page, and says there is more behind it.
    const more = await screen.findByRole("button", {
      name: "Show older conversations",
    });
    const [firstUrl] = fetchMock.mock.calls[0] as unknown as [string];
    expect(firstUrl).toContain("limit=20");
    expect(firstUrl).toContain("offset=0");
    expect(
      screen.queryByRole("button", { name: "Resume The oldest thread" }),
    ).toBeNull();

    await act(async () => {
      fireEvent.click(more);
    });

    // The 21st thread is reachable, and the page already read stays on screen.
    const [nextUrl] = fetchMock.mock.calls[1] as unknown as [string];
    expect(nextUrl).toContain("offset=20");
    expect(
      screen.getByRole("button", { name: "Resume The oldest thread" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume Thread 0" })).toBeTruthy();

    // That page came back short, so there is nothing left to offer.
    expect(
      screen.queryByRole("button", { name: "Show older conversations" }),
    ).toBeNull();
  });

  it("offers no next page when a book's conversations fit in one", async () => {
    stubServer([summary("conv1", "Ada Lovelace", 1)]);
    renderPanel();

    await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    expect(
      screen.queryByRole("button", { name: "Show older conversations" }),
    ).toBeNull();
  });

  it("resumes an asked conversation in the Ask panel without switching tabs", async () => {
    const onModeChange = vi.fn();
    stubServer([summary("conv1", "Ada Lovelace", 1)], {
      conv1: [turn("answer")],
    });
    renderPanel("ask", onModeChange);

    const before = screen.getByTestId("ask-panel-body").dataset.revision;
    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });

    // The Ask panel is pointed at that conversation and told to re-read.
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
    expect(screen.getByTestId("ask-panel-body").dataset.revision).not.toBe(before);
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("resumes a taught conversation in the Teach panel", async () => {
    const onModeChange = vi.fn();
    stubServer([summary("conv2", "Chapter 2", 3, ["c2.xhtml"])], {
      conv2: [turn("teach")],
    });
    renderPanel("ask", onModeChange);

    const row = await screen.findByRole("button", { name: "Resume Chapter 2" });
    await act(async () => {
      fireEvent.click(row);
    });

    // Its turns were taught, so the dock moves to the panel that can continue it
    // rather than leaving the reader on the wrong tab.
    expect(onModeChange).toHaveBeenCalledWith("teach");
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });

  it("resumes a section-scoped asked conversation in the Ask panel", async () => {
    const onModeChange = vi.fn();
    // A question can be asked inside one chapter: the conversation carries scope
    // anchors and is still an Ask thread, because scope is not mode.
    stubServer([summary("conv3", "About chapter 2", 2, ["c2.xhtml"])], {
      conv3: [turn("answer")],
    });
    renderPanel("ask", onModeChange);

    const row = await screen.findByRole("button", {
      name: "Resume About chapter 2",
    });
    await act(async () => {
      fireEvent.click(row);
    });

    // Resuming it into Teach would silently change what the next message does.
    expect(onModeChange).not.toHaveBeenCalled();
    expect(readActiveConversation("s1", "ask")).toBe("conv3");
    expect(readActiveConversation("s1", "teach")).toBeNull();
  });

  it("leaves the reader on the current tab when the thread cannot be read", async () => {
    const onModeChange = vi.fn();
    const rows = [summary("conv1", "Ada Lovelace", 1)];
    const fetchMock = vi.fn(async (url: string) =>
      url.startsWith("/api/conversations?")
        ? jsonResponse(200, rows)
        : jsonResponse(500, { detail: "boom" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderPanel("ask", onModeChange);

    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });

    // Nothing said the thread belongs elsewhere, so the reader is not moved —
    // and the resume still happens on the tab they are on.
    expect(onModeChange).not.toHaveBeenCalled();
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });

  it("starts a fresh thread on request without touching the other surface", async () => {
    stubServer([summary("conv1", "Ada Lovelace", 1)], {
      conv1: [turn("answer")],
    });
    renderPanel();

    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });
    expect(readActiveConversation("s1", "ask")).toBe("conv1");

    const before = screen.getByTestId("ask-panel-body").dataset.revision;
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));

    expect(readActiveConversation("s1", "ask")).toBeNull();
    expect(screen.getByTestId("ask-panel-body").dataset.revision).not.toBe(before);
  });
});
