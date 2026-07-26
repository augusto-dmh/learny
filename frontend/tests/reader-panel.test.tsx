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

  it("resumes a whole-book conversation in the Ask panel without switching tabs", async () => {
    const onModeChange = vi.fn();
    stubList([summary("conv1", "Ada Lovelace", 1)]);
    renderPanel("ask", onModeChange);

    const before = screen.getByTestId("ask-panel-body").dataset.revision;
    fireEvent.click(
      await screen.findByRole("button", { name: "Resume Ada Lovelace" }),
    );

    // The Ask panel is pointed at that conversation and told to re-read.
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
    expect(screen.getByTestId("ask-panel-body").dataset.revision).not.toBe(before);
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("resumes a section-scoped conversation in the Teach panel", async () => {
    const onModeChange = vi.fn();
    stubList([summary("conv2", "Chapter 2", 3, ["c2.xhtml"])]);
    renderPanel("ask", onModeChange);

    fireEvent.click(
      await screen.findByRole("button", { name: "Resume Chapter 2" }),
    );

    // A scoped thread is teaching, so the dock moves to the panel that can
    // continue it rather than leaving the reader on the wrong tab.
    expect(onModeChange).toHaveBeenCalledWith("teach");
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });

  it("starts a fresh thread on request without touching the other surface", async () => {
    stubList([summary("conv1", "Ada Lovelace", 1)]);
    renderPanel();

    fireEvent.click(
      await screen.findByRole("button", { name: "Resume Ada Lovelace" }),
    );
    expect(readActiveConversation("s1", "ask")).toBe("conv1");

    const before = screen.getByTestId("ask-panel-body").dataset.revision;
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));

    expect(readActiveConversation("s1", "ask")).toBeNull();
    expect(screen.getByTestId("ask-panel-body").dataset.revision).not.toBe(before);
  });
});
