// @vitest-environment jsdom

/**
 * D2 gate (component) — a citation renders as a chip that opens a popover with
 * its section-path breadcrumb and snippet, and an "Open in book" link into the
 * reader at that citation's `encodeURIComponent`-encoded anchor (a `/`- and
 * `#`-bearing anchor round-trips correctly). FE-16.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { CitationList } from "../app/components/citations";
import { type Citation } from "../app/lib/questions";

// Radix Popover reaches for ResizeObserver and the pointer-capture APIs that
// jsdom does not implement; stub them so the popover can open under test.
beforeAll(() => {
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

afterEach(() => {
  cleanup();
});

// An anchor carrying both a path separator and a fragment — the hostile case.
const citation: Citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: "part1/chapter-1.xhtml#core-idea",
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

describe("CitationList (D2)", () => {
  it("opens a popover with the breadcrumb, snippet, and an encoded reader link", () => {
    render(<CitationList sourceId="s1" citations={[citation]} />);

    // The popover content is not shown until the chip is clicked.
    expect(screen.queryByText("Chapter 1 › Core Idea")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );

    // Breadcrumb (section_path joined by " › ") and snippet render in the popover.
    expect(screen.getByText("Chapter 1 › Core Idea")).toBeTruthy();
    expect(screen.getByText("the first algorithm ever written")).toBeTruthy();

    // "Open in book" points at the reader with the anchor encoded exactly once:
    // "part1/chapter-1.xhtml#core-idea" → "part1%2Fchapter-1.xhtml%23core-idea".
    const link = screen.getByRole("link", { name: /open in book/i });
    expect(link.getAttribute("href")).toBe(
      "/sources/s1/read?anchor=part1%2Fchapter-1.xhtml%23core-idea",
    );

    // The snippet quotation renders under the reading-typography class — the
    // popover speaks in the book's voice (class presence, not pixels).
    const snippet = screen.getByText("the first algorithm ever written");
    expect(snippet.closest("blockquote")!.className).toContain("prose-reading");
  });

  it("renders nothing when there are no citations", () => {
    const { container } = render(
      <CitationList sourceId="s1" citations={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("CitationList as passage (RA-12)", () => {
  it("renders the verbatim passage in the reading serif and no retrieval machinery", () => {
    render(<CitationList sourceId="s1" citations={[citation]} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );

    // The passage renders as a verbatim blockquote under the reading-typography
    // class — the popover speaks in the book's voice, with its section-path locator.
    expect(screen.getByText("Chapter 1 › Core Idea")).toBeTruthy();
    const snippet = screen.getByText("the first algorithm ever written");
    expect(snippet.closest("blockquote")!.className).toContain("prose-reading");

    // The retrieval index behind the citation never leaks into the DOM: neither
    // the chunk id nor the similarity score is rendered anywhere.
    expect(document.body.textContent).not.toContain(citation.chunk_id);
    expect(document.body.textContent).not.toContain(String(citation.score));
  });

  it("shows an in-book jump button that invokes onShowInBook with the anchor (RA-13)", () => {
    const onShowInBook = vi.fn();
    render(
      <CitationList
        sourceId="s1"
        citations={[citation]}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );

    // With the callback, the action is an in-place button — not a navigating link.
    expect(screen.queryByRole("link", { name: /in book/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /show in book/i }));

    // It carries the citation's raw anchor to the reader, verbatim (no encoding).
    expect(onShowInBook).toHaveBeenCalledTimes(1);
    expect(onShowInBook).toHaveBeenCalledWith(citation.anchor);
  });

  it("falls back to the reader-route link when no callback is given", () => {
    render(<CitationList sourceId="s1" citations={[citation]} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );

    // Without the callback (outside the reader), the action is the encoded link.
    expect(screen.queryByRole("button", { name: /show in book/i })).toBeNull();
    const link = screen.getByRole("link", { name: /open in book/i });
    expect(link.getAttribute("href")).toBe(
      "/sources/s1/read?anchor=part1%2Fchapter-1.xhtml%23core-idea",
    );
  });
});

// A citation drawn from the user's own note: origin='note' plus the note identity.
const noteCitation: Citation = {
  chunk_id: "n1",
  source_id: "n1",
  section_path: [],
  anchor: "note:n1",
  page_span: null,
  snippet: "a distinctive fact from my own note",
  score: 0.9,
  origin: "note",
  note_id: "note-123",
  note_title: "My Insight",
};

describe("CitationList note citations (NL-03)", () => {
  it("renders a note citation distinctly, linking into the note and never the book", () => {
    render(<CitationList sourceId="s1" citations={[noteCitation]} />);

    // The note chip carries its own label (not the book "Citation:" one).
    fireEvent.click(screen.getByRole("button", { name: "Your note: My Insight" }));

    // "Your note — <title>" label and the cited passage render in the popover.
    expect(screen.getByText("Your note — My Insight")).toBeTruthy();
    expect(
      screen.getByText("a distinctive fact from my own note"),
    ).toBeTruthy();

    // The action links into the note detail — never any into-the-book action.
    const link = screen.getByRole("link", { name: /open note/i });
    expect(link.getAttribute("href")).toBe("/notes/note-123");
    expect(screen.queryByRole("link", { name: /open in book/i })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /show in book/i }),
    ).toBeNull();
  });

  it("renders both a book and a note citation in a mixed list, each with its own action", () => {
    const onShowInBook = vi.fn();
    render(
      <CitationList
        sourceId="s1"
        citations={[citation, noteCitation]}
        onShowInBook={onShowInBook}
      />,
    );

    // The book chip still opens the in-book action (unchanged).
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );
    expect(screen.getByRole("button", { name: /show in book/i })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /open note/i })).toBeNull();

    // The note chip opens the into-the-note action instead.
    fireEvent.click(screen.getByRole("button", { name: "Your note: My Insight" }));
    const noteLink = screen.getByRole("link", { name: /open note/i });
    expect(noteLink.getAttribute("href")).toBe("/notes/note-123");
  });
});
