// @vitest-environment jsdom

/**
 * A (RA-01/02/03) — the reader side-panel shell hosts the dock's tab strip and a
 * close control. It renders the body for the active tab, marks that tab as
 * selected, and reports tab switches and close through its callbacks (the parent
 * turns those into URL changes). Open state and the active tab are driven entirely
 * by props derived from `?panel=`, so the shell itself is a pure function of `tab`.
 *
 * The strip is Chat | Notes | Review. Chat holds the conversation list; Ask and
 * Teach are composer modes armed by `?panel=` aliases, not extra tabs. Per-surface
 * thread state must survive a trip through Notes and Review.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ReaderPanel,
  composerModeFromParam,
  dockTabFromParam,
  type DockTab,
  type PanelMode,
} from "../app/components/reader-panel";
import { readActiveConversation } from "../app/lib/active-conversation";
import { LG_MIN_WIDTH_PX } from "../hooks/use-below-lg";

// The shell test covers tabs, close, and which mode's body renders — not the
// chat internals (unit-tested in ask-panel.test.tsx, which pull in AI-Elements).
// Stub the ported bodies to their markers so the shell stays a pure unit test;
// each stub also surfaces its `onShowInBook` prop through a button so the shell's
// forwarding of the citation-jump callback to BOTH modes can be driven by a click.
type StubProps = {
  revision?: number;
  onShowInBook?: (anchor: string) => void;
  onAskAboutThis?: () => void;
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
  TeachPanel: ({ revision, onShowInBook, onAskAboutThis }: StubProps) => (
    <div data-testid="teach-panel-body" data-revision={revision}>
      <button type="button" onClick={() => onShowInBook?.("teach#anchor")}>
        teach-show-in-book
      </button>
      <button type="button" onClick={() => onAskAboutThis?.()}>
        Ask about this
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
  lastTurnMode: "answer" | "teach" | null = "answer",
) {
  return {
    id,
    source_id: "s1",
    source_title: "A Book",
    title,
    scope_anchors: scopeAnchors,
    include_notes: false,
    turn_count: turnCount,
    last_turn_mode: lastTurnMode,
    created_at: "now",
    updated_at: "now",
  };
}

/**
 * The dock always loads the book's conversations, and — for the counts its two
 * other tabs carry — this book's notes and due cards. Default all three to empty.
 */
function stubList(rows: unknown[] = []) {
  const fetchMock = vi.fn(async (url: string) =>
    jsonResponse(200, url.startsWith("/api/conversations") ? rows : []),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The conversation requests the dock made, in order. */
function conversationCalls(fetchMock: { mock: { calls: unknown[] } }) {
  return (fetchMock.mock.calls as unknown[][])
    .map((call) => String(call[0]))
    .filter((url) => url.startsWith("/api/conversations"));
}

/**
 * The list, and nothing else: a resume reads the mode off the row it was given,
 * so any other request the shell makes is one it should not be making. Fetching
 * the conversation to learn where it resumes would drag every turn and every
 * citation across, and the panel then loads the same payload again.
 */
function stubServer(rows: ReturnType<typeof summary>[]) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith("/api/notes") || url.startsWith("/api/reviews/due")) {
      // The tab counts, which every dock render loads.
      return jsonResponse(200, []);
    }
    if (!url.startsWith("/api/conversations?")) {
      throw new Error(`unexpected fetch: ${url}`);
    }
    return jsonResponse(200, rows);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * Drive the AD-280 breakpoint in JS. Tailwind `lg` is 1024px; below that the
 * dock is a bottom sheet. jsdom has no CSS media queries, so tests that only
 * inspect class names cannot prove READ-22.
 */
function stubViewportWidth(width: number) {
  window.matchMedia = (query: string) => {
    const maxWidth = query.match(/max-width:\s*(\d+)px/i);
    const matches = maxWidth ? width <= Number(maxWidth[1]) : false;
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  };
}

function sheetContent(): HTMLElement | null {
  return document.querySelector<HTMLElement>("[data-slot='sheet-content']");
}

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
});

beforeEach(() => {
  stubList();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  Reflect.deleteProperty(window, "matchMedia");
});

describe("dockTabFromParam (TUTOR-27/28)", () => {
  it("maps ask, teach, and chat onto Chat, and leaves Notes and Review as themselves", () => {
    expect(dockTabFromParam("ask")).toBe("chat");
    expect(dockTabFromParam("teach")).toBe("chat");
    expect(dockTabFromParam("chat")).toBe("chat");
    expect(dockTabFromParam("notes")).toBe("notes");
    expect(dockTabFromParam("review")).toBe("review");
    expect(dockTabFromParam("nowhere")).toBeNull();
    expect(dockTabFromParam(null)).toBeNull();
  });
});

describe("composerModeFromParam (TUTOR-28)", () => {
  it("arms Answer from ask, Tutor from teach, and last-used or Answer from chat", () => {
    expect(composerModeFromParam("ask", "teach")).toBe("ask");
    expect(composerModeFromParam("teach", "ask")).toBe("teach");
    expect(composerModeFromParam("chat", "teach")).toBe("teach");
    expect(composerModeFromParam("chat", null)).toBe("ask");
  });
});

describe("ReaderPanel shell (RA-01/02/03, TUTOR-27/28)", () => {
  it("offers Chat, Notes, and Review — not Ask or Teach tabs (TUTOR-27)", () => {
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(
      screen.getAllByRole("tab").map((tab) => tab.textContent?.trim()),
    ).toEqual(["Chat", "Notes", "Review"]);
    expect(screen.queryByRole("tab", { name: "Ask" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Teach" })).toBeNull();
    expect(screen.getByRole("button", { name: "Close panel" })).toBeTruthy();
  });

  it("opens Chat with Answer armed when ?panel=ask (TUTOR-28)", () => {
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Chat" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("opens Chat with Tutor armed when ?panel=teach (TUTOR-28)", () => {
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="teach"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("ask-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Chat" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("Ask about this arms a new Answer conversation without posting onto Tutor (TUTOR-33)", () => {
    const fetchMock = stubList();
    const onTabChange = vi.fn();
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="teach"
        onTabChange={onTabChange}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Ask about this" }));

    expect(onTabChange).toHaveBeenCalledWith("ask");
    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
    expect(readActiveConversation("s1", "ask")).toBeNull();
    expect(
      (fetchMock.mock.calls as unknown[][]).some((call) => {
        const url = String(call[0]);
        const init = call[1] as RequestInit | undefined;
        return url.includes("/turns/stream") && init?.method === "POST";
      }),
    ).toBe(false);
  });

  it("opens Chat with Answer when ?panel=chat and nothing was used last (TUTOR-28)", () => {
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="chat"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
  });

  it("opens Chat with last-used Tutor when ?panel=chat follows a teach visit (TUTOR-28)", () => {
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="teach"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();

    rerender(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="chat"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("ask-panel-body")).toBeNull();
  });

  it("lets ?panel=ask arm Answer even when last-used was Tutor (TUTOR-28)", () => {
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="teach"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    rerender(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
  });

  it("reports the chosen strip tab when a tab is clicked (RA-03)", () => {
    const onModeChange = vi.fn();
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={onModeChange}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(onModeChange).toHaveBeenCalledWith("notes");
  });

  it("reports a close request when the close control is clicked (RA-03)", () => {
    const onClose = vi.fn();
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("forwards the show-in-book callback to the armed composer body (RA-13/14)", () => {
    const onShowInBook = vi.fn();

    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "ask-show-in-book" }));
    expect(onShowInBook).toHaveBeenCalledWith("ask#anchor");

    rerender(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="teach"
        onTabChange={() => {}}
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
    panelParam: string | null = "ask",
    onModeChange: (tab: DockTab | PanelMode) => void = () => {},
  ) {
    return render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam={panelParam}
        onTabChange={onModeChange}
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
    const fetchMock = vi.fn(async (url: string) => {
      if (!url.startsWith("/api/conversations")) {
        return jsonResponse(200, []);
      }
      return jsonResponse(200, url.includes("offset=20") ? secondPage : firstPage);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();

    // The dock asks for one bounded page, and says there is more behind it.
    const more = await screen.findByRole("button", {
      name: "Show older conversations",
    });
    const [firstUrl] = conversationCalls(fetchMock);
    expect(firstUrl).toContain("limit=20");
    expect(firstUrl).toContain("offset=0");
    expect(
      screen.queryByRole("button", { name: "Resume The oldest thread" }),
    ).toBeNull();

    await act(async () => {
      fireEvent.click(more);
    });

    // The 21st thread is reachable, and the page already read stays on screen.
    expect(conversationCalls(fetchMock)[1]).toContain("offset=20");
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

  it("resumes an asked conversation in Answer without switching the Chat tab (TUTOR-31)", async () => {
    const onModeChange = vi.fn();
    const fetchMock = stubServer([summary("conv1", "Ada Lovelace", 1)]);
    renderPanel("ask", onModeChange);

    const before = screen.getByTestId("ask-panel-body").dataset.revision;
    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });

    expect(readActiveConversation("s1", "ask")).toBe("conv1");
    expect(screen.getByTestId("ask-panel-body").dataset.revision).not.toBe(before);
    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(onModeChange).not.toHaveBeenCalled();
    expect(conversationCalls(fetchMock)).toHaveLength(1);
  });

  it("resumes a taught conversation in Tutor even when the alias was ask (TUTOR-31)", async () => {
    const onModeChange = vi.fn();
    stubServer([summary("conv2", "Chapter 2", 3, ["c2.xhtml"], "teach")]);
    renderPanel("ask", onModeChange);

    const row = await screen.findByRole("button", { name: "Resume Chapter 2" });
    await act(async () => {
      fireEvent.click(row);
    });

    expect(onModeChange).toHaveBeenCalledWith("teach");
    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("ask-panel-body")).toBeNull();
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });

  it("resumes an answered conversation in Answer even when the alias was teach (TUTOR-31)", async () => {
    const onModeChange = vi.fn();
    stubServer([summary("conv1", "Ada Lovelace", 1, [], "answer")]);
    renderPanel("teach", onModeChange);

    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });

    expect(onModeChange).toHaveBeenCalledWith("ask");
    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });

  it("resumes a section-scoped asked conversation in the Ask panel", async () => {
    const onModeChange = vi.fn();
    // A question can be asked inside one chapter: the conversation carries scope
    // anchors and is still an Ask thread, because scope is not mode.
    stubServer([summary("conv3", "About chapter 2", 2, ["c2.xhtml"], "answer")]);
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

  it("leaves the reader on the current tab when no turn speaks for the thread", async () => {
    const onModeChange = vi.fn();
    stubServer([summary("conv1", "Ada Lovelace", 0, [], null)]);
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
    stubServer([summary("conv1", "Ada Lovelace", 1)]);
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

describe("ReaderPanel tabs that hold no conversation", () => {
  it("keeps the conversation list to the tabs that can hold a thread", async () => {
    const fetchMock = stubList([summary("conv1", "Ada Lovelace", 1)]);
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );
    await screen.findByRole("button", { name: "Resume Ada Lovelace" });

    for (const tab of ["notes", "review"] as const) {
      await act(async () => {
        rerender(
          <ReaderPanel
            sourceId="s1"
            csrf="csrf-xyz"
            tab={tab}
            onTabChange={() => {}}
            onClose={() => {}}
          />,
        );
      });

      // Neither tab is a place a thread can be resumed or started, so the list
      // that offers both is absent rather than decorative.
      expect(
        screen.queryByRole("button", { name: "Resume Ada Lovelace" }),
      ).toBeNull();
      expect(
        screen.queryByRole("button", { name: "New conversation" }),
      ).toBeNull();
    }

    // And nothing re-asked the server for threads while they were open.
    expect(conversationCalls(fetchMock)).toHaveLength(1);
  });

  it("leaves the open Ask thread exactly where it was after a trip through Notes", async () => {
    stubList([summary("conv1", "Ada Lovelace", 1)]);
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    const row = await screen.findByRole("button", { name: "Resume Ada Lovelace" });
    await act(async () => {
      fireEvent.click(row);
    });
    const revision = screen.getByTestId("ask-panel-body").dataset.revision;
    expect(readActiveConversation("s1", "ask")).toBe("conv1");

    for (const tab of ["notes", "review", "chat"] as const) {
      await act(async () => {
        rerender(
          <ReaderPanel
            sourceId="s1"
            csrf="csrf-xyz"
            tab={tab}
            panelParam={tab === "chat" ? "ask" : undefined}
            onTabChange={() => {}}
            onClose={() => {}}
          />,
        );
      });
    }

    // Back on Chat, the same thread is still the open one and the panel was never
    // told to re-read: visiting a tab with no conversation state disturbed none.
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
    expect(screen.getByTestId("ask-panel-body").dataset.revision).toBe(revision);
  });
});

describe("ReaderPanel phone sheet (READ-22)", () => {
  it("renders an open dock as a bottom sheet below lg, not a 26rem side column", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX - 1);
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    const sheet = await waitFor(() => {
      const node = sheetContent();
      expect(node).not.toBeNull();
      return node!;
    });
    expect(sheet.getAttribute("data-side")).toBe("bottom");
    expect(sheet.className.split(/\s+/)).not.toContain("w-[26rem]");
    const panel = screen.getByTestId("reader-panel");
    expect(panel.className.split(/\s+/)).not.toContain("w-[26rem]");
    expect(panel.className.split(/\s+/)).not.toContain("max-xl:fixed");
    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
  });

  it("keeps the overlay side dock at lg and above, not a full-width bottom sheet", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX);
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("reader-panel")).toBeTruthy();
    });
    expect(sheetContent()).toBeNull();
    const panel = screen.getByTestId("reader-panel");
    const classes = panel.className.split(/\s+/);
    expect(classes).toContain("w-[26rem]");
    expect(classes).toContain("max-xl:fixed");
    expect(classes).toContain("max-xl:inset-y-0");
    expect(classes).toContain("max-xl:right-0");
    expect(classes).not.toContain("shrink-0");
    expect(classes).toContain("xl:shrink-0");
  });
});

describe("ReaderPanel sheet close target (READ-25)", () => {
  it("sizes the sheet close control to at least 44px", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX - 1);
    render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        tab="chat"
        panelParam="ask"
        onTabChange={() => {}}
        onClose={() => {}}
      />,
    );

    const close = await waitFor(() => screen.getByRole("button", { name: "Close" }));
    expect(Number.parseFloat(getComputedStyle(close).minWidth)).toBeGreaterThanOrEqual(44);
    expect(Number.parseFloat(getComputedStyle(close).minHeight)).toBeGreaterThanOrEqual(44);
  });
});
