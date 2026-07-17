// @vitest-environment jsdom

/**
 * D2 gate (component) — a citation renders as a chip that opens a popover with
 * its section-path breadcrumb and snippet, and an "Open in book" link into the
 * reader at that citation's `encodeURIComponent`-encoded anchor (a `/`- and
 * `#`-bearing anchor round-trips correctly). FE-16.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

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
  });

  it("renders nothing when there are no citations", () => {
    const { container } = render(
      <CitationList sourceId="s1" citations={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
