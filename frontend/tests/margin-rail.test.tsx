// @vitest-environment jsdom

/**
 * E1 gate (component) — the margin rail lists the *loaded chapter's* highlights
 * and notes in document order (CAP-18), labels an entry that carries a note body
 * with that note's title (CAP-19), gives an orphaned highlight the shared orphan
 * indicator while rendering it from its stored quote snapshot (CAP-20), jumps to a
 * painted highlight (CAP-21) but never attempts a scroll for an orphaned one —
 * offering its origin note instead (CAP-22) — and renders an empty state rather
 * than an empty column when the chapter has nothing in it (CAP-23).
 *
 * Chapter scope is the load-bearing assertion here: the rail is reading-column
 * furniture, so a highlight belonging to another chapter must not appear in it
 * even though the reader fetches the whole source's highlights in one call.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarginRail } from "../app/components/margin-rail";
import type { SourceHighlightView } from "../app/lib/reading";

const S1 = "part1/ch1.xhtml#s1";
const S2 = "part1/ch1.xhtml#s2";
const OTHER_CHAPTER = "part1/ch2.xhtml#s1";

/** The loaded chapter's sections, in document order. */
const CHAPTER_ANCHORS = [S1, S2];

function highlight(
  overrides: Partial<SourceHighlightView> & { note_id: string },
): SourceHighlightView {
  return {
    note_title: "Untitled",
    has_body: false,
    anchor: S1,
    quote_exact: "a quote",
    quote_prefix: "",
    quote_suffix: "",
    status: "active",
    ...overrides,
  };
}

afterEach(cleanup);

describe("MarginRail chapter scope (CAP-18)", () => {
  it("lists only the loaded chapter's highlights, in document order", () => {
    // Deliberately supplied out of order, and with one belonging to the *next*
    // chapter — the reader fetches every highlight on the source in one call.
    render(
      <MarginRail
        highlights={[
          highlight({ note_id: "n2", anchor: S2, quote_exact: "second section" }),
          highlight({
            note_id: "n3",
            anchor: OTHER_CHAPTER,
            quote_exact: "another chapter entirely",
          }),
          highlight({ note_id: "n1", anchor: S1, quote_exact: "first section" }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    const quotes = screen
      .getAllByTestId("rail-quote")
      .map((node) => node.textContent);
    expect(quotes).toEqual(["first section", "second section"]);
    // The out-of-chapter highlight is absent, not merely last.
    expect(screen.queryByText("another chapter entirely")).toBeNull();
  });

  it("keeps the server's order for several highlights inside one section", () => {
    render(
      <MarginRail
        highlights={[
          highlight({ note_id: "n1", anchor: S1, quote_exact: "earlier in s1" }),
          highlight({ note_id: "n2", anchor: S1, quote_exact: "later in s1" }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(
      screen.getAllByTestId("rail-quote").map((node) => node.textContent),
    ).toEqual(["earlier in s1", "later in s1"]);
  });
});

describe("MarginRail entry rendering (CAP-19/20)", () => {
  it("shows the origin note's title when the highlight carries a note body", () => {
    render(
      <MarginRail
        highlights={[
          highlight({
            note_id: "n1",
            note_title: "Why Ada matters",
            has_body: true,
            quote_exact: "Ada wrote the first algorithm.",
          }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(screen.getByText("Why Ada matters")).toBeTruthy();
  });

  it("identifies a bare highlight by its quote, with no note title", () => {
    render(
      <MarginRail
        highlights={[
          highlight({
            note_id: "n1",
            note_title: "Ada wrote the first algorithm.",
            has_body: false,
            quote_exact: "Ada wrote the first algorithm.",
          }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    // The quote is the only label — the title is not repeated beside it.
    expect(
      screen.getAllByText("Ada wrote the first algorithm.").length,
    ).toBe(1);
  });

  it("renders an orphaned highlight from its snapshot with the shared orphan indicator", () => {
    render(
      <MarginRail
        highlights={[
          highlight({
            note_id: "n1",
            status: "orphaned",
            quote_exact: "a passage the re-ingest lost",
          }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    // The quote snapshot is all that survives of the passage, and it renders.
    expect(screen.getByText("a passage the re-ingest lost")).toBeTruthy();
    // The orphan treatment is the shared badge, not a rail-local restyling.
    expect(screen.getByTestId("anchor-status-orphaned")).toBeTruthy();
  });

  it("marks a stale highlight without treating it as orphaned", () => {
    render(
      <MarginRail
        highlights={[highlight({ note_id: "n1", status: "stale" })]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(screen.getByTestId("anchor-status-stale")).toBeTruthy();
    expect(screen.queryByTestId("anchor-status-orphaned")).toBeNull();
  });

  it("shows no status badge for an active highlight", () => {
    render(
      <MarginRail
        highlights={[highlight({ note_id: "n1", status: "active" })]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("anchor-status-active")).toBeNull();
  });
});

describe("MarginRail activation (CAP-21/22)", () => {
  it("jumps to the entry's anchor when its highlight is painted in the chapter", () => {
    const onJump = vi.fn();
    render(
      <MarginRail
        highlights={[highlight({ note_id: "n1", anchor: S2 })]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={onJump}
      />,
    );

    fireEvent.click(screen.getByTestId("rail-entry").querySelector("button")!);

    expect(onJump).toHaveBeenCalledWith(S2);
  });

  it("never attempts a scroll for an orphaned entry, offering its note instead", () => {
    const onJump = vi.fn();
    render(
      <MarginRail
        highlights={[
          highlight({ note_id: "n7", anchor: S1, status: "orphaned" }),
        ]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={onJump}
      />,
    );

    const entry = screen.getByTestId("rail-entry");
    // There is no jump control at all — the entry is a link to the origin note,
    // so "does not scroll" holds structurally rather than by a handler check.
    expect(entry.querySelector("button")).toBeNull();
    const link = entry.querySelector("a")!;
    expect(link.getAttribute("href")).toBe("/notes/n7");

    fireEvent.click(link);
    expect(onJump).not.toHaveBeenCalled();
  });
});

describe("MarginRail empty state (CAP-23)", () => {
  it("says the chapter has nothing in it rather than rendering an empty column", () => {
    render(
      <MarginRail
        highlights={[]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(screen.getByText("Nothing highlighted in this chapter yet.")).toBeTruthy();
    expect(screen.queryAllByTestId("rail-entry")).toHaveLength(0);
  });

  it("shows the empty state when every highlight belongs to another chapter", () => {
    render(
      <MarginRail
        highlights={[highlight({ note_id: "n1", anchor: OTHER_CHAPTER })]}
        chapterAnchors={CHAPTER_ANCHORS}
        onJump={vi.fn()}
      />,
    );

    expect(screen.getByText("Nothing highlighted in this chapter yet.")).toBeTruthy();
  });
});
