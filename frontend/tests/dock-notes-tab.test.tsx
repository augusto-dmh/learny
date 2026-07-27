// @vitest-environment jsdom

/**
 * The dock's Notes tab (WSN-01..05) — this book's notes, beside the page they came
 * from.
 *
 * What a reader needs from the tab is to recognise a note without opening it: its
 * title, the passage it was taken at, and the words themselves. What they must not
 * see is another book's notes, the same note twice, or a page number the book can
 * no longer back up. The tab's count says how many notes this book holds — an
 * inventory, so an empty book carries no badge at all rather than a zero.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReaderPanel } from "../app/components/reader-panel";
import { type NoteSummary } from "../app/lib/notes";

// The tab is the unit here; the conversation surfaces are stubbed so their chat
// internals stay out of it (they are covered in their own files).
vi.mock("../app/components/ask-panel", () => ({
  AskPanel: () => <div data-testid="ask-panel-body" />,
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: () => <div data-testid="teach-panel-body" />,
}));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A note row as the book-scoped notes list returns it. */
function note(
  id: string,
  title: string,
  anchor: NoteSummary["anchor"],
): NoteSummary {
  return {
    id,
    title,
    tags: [],
    anchor_statuses: anchor ? [anchor.status] : [],
    anchor,
    created_at: "now",
    updated_at: "now",
  };
}

function passage(
  sectionTitle: string,
  quote: string,
  page: number | null,
  status = "active",
): NonNullable<NoteSummary["anchor"]> {
  return {
    anchor: `${sectionTitle}.xhtml#s1`,
    section_title: sectionTitle,
    section_path: ["Part One", sectionTitle],
    quote_exact: quote,
    status,
    page,
  };
}

/** Answer the book's notes list; every other dock request settles empty. */
function stubNotes(rows: NoteSummary[]) {
  const fetchMock = vi.fn(async (url: string) =>
    jsonResponse(200, url.startsWith("/api/notes") ? rows : []),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderNotesTab(
  props: { onShowInBook?: (anchor: string) => void; notesToken?: number } = {},
) {
  return render(
    <ReaderPanel
      sourceId="s1"
      csrf="csrf-xyz"
      tab="notes"
      onTabChange={() => {}}
      onClose={() => {}}
      {...props}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("the dock's Notes tab", () => {
  it("lists this book's notes, each with the passage it came from", async () => {
    const fetchMock = stubNotes([
      note("n2", "On mechanism", passage("Prefácio", "the analytical engine", 62)),
      note("n1", "On beginnings", passage("Chapter One", "the first algorithm", 7)),
    ]);
    renderNotesTab();

    // Only this book's notes were ever asked for.
    await waitFor(() =>
      expect(screen.getByText("On mechanism")).toBeTruthy(),
    );
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("/api/notes?source_id=s1"),
      ),
    ).toBe(true);

    // The server's order — newest-edited first — is the reader's order, and each
    // row names itself, where it came from, and the words it was taken from.
    const rows = Array.from(
      screen
        .getByRole("list", { name: "Notes on this book" })
        .querySelectorAll("li"),
    );
    expect(
      rows.map((row) => Array.from(row.childNodes, (n) => n.textContent)),
    ).toEqual([
      ["On mechanism", "Prefácio · p. 62", "the analytical engine"],
      ["On beginnings", "Chapter One · p. 7", "the first algorithm"],
    ]);
  });

  it("shows a note anchored to the book more than once exactly once", async () => {
    // Two anchors on this book, one note: the list is note-shaped, so it is one
    // row carrying the passage the note came from — the earliest of them.
    const twice = note(
      "n1",
      "On beginnings",
      passage("Chapter One", "the first algorithm", 7),
    );
    stubNotes([{ ...twice, anchor_statuses: ["active", "active"] }]);
    renderNotesTab();

    await screen.findByText("On beginnings");
    expect(screen.getAllByText("On beginnings")).toHaveLength(1);
    expect(
      screen
        .getByRole("list", { name: "Notes on this book" })
        .querySelectorAll("li"),
    ).toHaveLength(1);
  });

  it("keeps a note whose passage has orphaned, showing its words and no page", async () => {
    stubNotes([
      note(
        "n1",
        "On beginnings",
        passage("Chapter One", "the first algorithm", null, "orphaned"),
      ),
    ]);
    renderNotesTab();

    // The note survives the passage: its quote is still there, and no page number
    // is invented for an anchor the book can no longer resolve.
    await screen.findByText("On beginnings");
    expect(screen.getByText("the first algorithm")).toBeTruthy();
    expect(screen.getByText("Chapter One")).toBeTruthy();
    expect(screen.queryByText(/p\./)).toBeNull();
  });

  it("draws no quote block for a note taken from a section rather than a selection", async () => {
    stubNotes([
      note("n1", "On the whole chapter", passage("Chapter One", "", 12)),
    ]);
    const { container } = renderNotesTab();

    // An answer saved when its citation carried no quotable words anchors the
    // section itself, so there is no quote — and an empty bordered block is worse
    // than none. The row still says where it came from.
    await screen.findByText("On the whole chapter");
    expect(screen.getByText("Chapter One · p. 12")).toBeTruthy();
    expect(container.querySelector("blockquote")).toBeNull();
  });

  it("reaches back to the passage a note came from without leaving the book", async () => {
    const onShowInBook = vi.fn();
    stubNotes([
      note("n1", "On beginnings", passage("Chapter One", "the algorithm", 7)),
    ]);
    renderNotesTab({ onShowInBook });

    const where = await screen.findByRole("button", {
      name: "Chapter One · p. 7",
    });
    where.click();

    expect(onShowInBook).toHaveBeenCalledWith("Chapter One.xhtml#s1");
  });

  it("invites the first note when the book has none", async () => {
    stubNotes([]);
    renderNotesTab();

    expect(
      await screen.findByText(
        "Notes on this book only. Select a passage to start a new one — every note keeps the passage it came from.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("list", { name: "Notes on this book" }),
    ).toBeNull();
  });

  it("carries the book's note count on the tab", async () => {
    stubNotes([
      note("n2", "On mechanism", passage("Prefácio", "the engine", 62)),
      note("n1", "On beginnings", passage("Chapter One", "the algorithm", 7)),
    ]);
    renderNotesTab();

    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: /^Notes/ }).textContent?.trim(),
      ).toBe("Notes2"),
    );
  });

  it("carries no count at all when the book holds no notes", async () => {
    stubNotes([]);
    renderNotesTab();

    // An empty tab is empty, not a zero: the count is inventory, not a score.
    await screen.findByText(/Notes on this book only\./);
    expect(screen.getByRole("tab", { name: /^Notes/ }).textContent?.trim()).toBe(
      "Notes",
    );
  });

  it("shows a note written from the page without a reload", async () => {
    const first = note(
      "n1",
      "On beginnings",
      passage("Chapter One", "the first algorithm", 7),
    );
    const second = note(
      "n2",
      "On mechanism",
      passage("Prefácio", "the analytical engine", 62),
    );
    let rows = [first];
    const fetchMock = vi.fn(async (url: string) =>
      jsonResponse(200, url.startsWith("/api/notes") ? rows : []),
    );
    vi.stubGlobal("fetch", fetchMock);

    const view = renderNotesTab({ notesToken: 0 });
    await screen.findByText("On beginnings");

    // The reader captures a passage while the tab is open; the host says so.
    rows = [second, first];
    await act(async () => {
      view.rerender(
        <ReaderPanel
          sourceId="s1"
          csrf="csrf-xyz"
          tab="notes"
          onTabChange={() => {}}
          onClose={() => {}}
          notesToken={1}
        />,
      );
    });

    expect(await screen.findByText("On mechanism")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /^Notes/ }).textContent?.trim()).toBe(
      "Notes2",
    );
  });

  it("says so when this book's notes cannot be loaded", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.startsWith("/api/notes")
        ? jsonResponse(404, { detail: "Source not found." })
        : jsonResponse(200, []),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderNotesTab();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Source not found.",
    );
  });
});
