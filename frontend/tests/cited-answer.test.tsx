// @vitest-environment jsdom

/**
 * The answer and its evidence (ANSW-07/08) — a `[^n]` marker in the answer text
 * renders as a numbered mark inside the prose, and activating a mark or its chip
 * opens that citation's passage in flow beneath the answer: one region, clamped,
 * with the breadcrumb, the verbatim snippet, and the way into the book. A marker
 * with no citation behind it stays plain text, and nothing is ever laid over the
 * reading column.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CitedAnswer } from "../app/components/cited-answer";
import { type Citation } from "../app/lib/citations";

afterEach(() => {
  cleanup();
});

const first: Citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: "part1/chapter-1.xhtml#core-idea",
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

const second: Citation = {
  ...first,
  chunk_id: "c2",
  section_path: ["Chapter 2", "The Engine"],
  anchor: "part1/chapter-2.xhtml#engine",
  snippet: "the analytical engine was never built",
  score: 0.02,
};

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

describe("CitedAnswer inline marks (ANSW-07)", () => {
  it("renders a marker as a mark in the prose whose activation opens the passage beneath", () => {
    const onShowInBook = vi.fn();
    const { container } = render(
      <CitedAnswer
        sourceId="s1"
        text="Ada Lovelace wrote it.[^1] The engine came later."
        citations={[first]}
        onShowInBook={onShowInBook}
      />,
    );

    // The mark sits inside the sentence it belongs to, not after the answer.
    const mark = screen.getByRole("button", { name: "Citation 1" });
    const paragraph = mark.closest("p")!;
    expect(paragraph.textContent).toContain("Ada Lovelace wrote it.");
    expect(paragraph.textContent).toContain("The engine came later.");
    // The marker itself is gone from the prose — it reads as a mark, not as text.
    expect(paragraph.textContent).not.toContain("[^1]");

    // Nothing is open until a mark is activated.
    expect(screen.queryByTestId("citation-passage")).toBeNull();

    fireEvent.click(mark);

    // The passage opens beneath the answer, in the same tree as the message —
    // never mounted over the reading column the way the old overlay was.
    const passage = screen.getByTestId("citation-passage");
    expect(container.contains(passage)).toBe(true);
    expect(passage.textContent).toContain("Chapter 1 › Core Idea");
    const snippet = screen.getByText("the first algorithm ever written");
    expect(snippet.closest("blockquote")!.className).toContain("prose-reading");
    // Clamped, so a long passage scrolls in its own box instead of pushing the
    // answer off screen.
    expect(snippet.closest("blockquote")!.className).toContain("max-h-");
    expect(snippet.closest("blockquote")!.className).toContain("overflow-y-auto");

    // "Show in book" carries the citation's raw anchor to the reader (RA-13).
    fireEvent.click(screen.getByRole("button", { name: /show in book/i }));
    expect(onShowInBook).toHaveBeenCalledTimes(1);
    expect(onShowInBook).toHaveBeenCalledWith(first.anchor);

    // The retrieval index behind the citation never reaches the DOM.
    expect(document.body.textContent).not.toContain(first.chunk_id);
    expect(document.body.textContent).not.toContain(String(first.score));
  });

  it("leaves a marker with no citation behind it as plain text", () => {
    render(
      <CitedAnswer
        sourceId="s1"
        text="A claim the model grounded and one it did not.[^4]"
        citations={[first]}
      />,
    );

    // A dropped grounding leaves prose, not a control that leads nowhere.
    expect(screen.queryByRole("button", { name: "Citation 4" })).toBeNull();
    expect(document.body.textContent).toContain("[^4]");
  });

  it("renders markers as plain text when the turn carries no citations at all", () => {
    render(
      <CitedAnswer sourceId="s1" text="Still streaming.[^1]" citations={null} />,
    );

    expect(screen.queryByRole("button", { name: "Citation 1" })).toBeNull();
    expect(screen.queryByLabelText("citations")).toBeNull();
    expect(document.body.textContent).toContain("[^1]");
  });
});

describe("CitedAnswer passage region (ANSW-08)", () => {
  it("keeps one passage open, whichever mark or chip selected it", () => {
    render(
      <CitedAnswer
        sourceId="s1"
        text="First claim.[^1] Second claim.[^2]"
        citations={[first, second]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Citation 1" }));
    expect(screen.getByText("the first algorithm ever written")).toBeTruthy();

    // The chip row is the same selection, not a second one: choosing from it
    // swaps the open passage rather than stacking another box.
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 2 › The Engine" }),
    );
    expect(screen.getAllByTestId("citation-passage")).toHaveLength(1);
    expect(
      screen.getByText("the analytical engine was never built"),
    ).toBeTruthy();
    expect(screen.queryByText("the first algorithm ever written")).toBeNull();

    // And activating the open citation again closes it.
    fireEvent.click(screen.getByRole("button", { name: "Citation 2" }));
    expect(screen.queryByTestId("citation-passage")).toBeNull();
  });

  it("keeps the chip row as the answer's evidence inventory when the text has no markers", () => {
    // An answer whose text carries no markers still reaches its evidence — the
    // chips are the fallback, not decoration (spec AC4).
    render(
      <CitedAnswer
        sourceId="s1"
        text="An answer with no inline marks."
        citations={[first]}
      />,
    );

    expect(screen.queryByRole("button", { name: "Citation 1" })).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );
    expect(screen.getByText("the first algorithm ever written")).toBeTruthy();
  });

  it("keeps an inline mark's open state truthful, and points it at the passage", () => {
    // The mark lives inside the answer body, which is memoized on its text and does
    // not re-render when the selection changes — so its state has to arrive by a
    // channel that reaches through that memo, or it would announce whatever it was
    // born with forever.
    render(
      <CitedAnswer
        sourceId="s1"
        text="Ada Lovelace wrote it.[^1]"
        citations={[first]}
      />,
    );
    const mark = screen.getByRole("button", { name: "Citation 1" });

    expect(mark.getAttribute("aria-expanded")).toBe("false");
    expect(mark.getAttribute("aria-controls")).toBeNull();

    fireEvent.click(mark);

    const passage = screen.getByTestId("citation-passage");
    expect(mark.getAttribute("aria-expanded")).toBe("true");
    expect(mark.getAttribute("aria-controls")).toBe(passage.id);
    // The chip for the same citation opened the same one region, so it says so too.
    const chip = screen.getByRole("button", {
      name: "Citation: Chapter 1 › Core Idea",
    });
    expect(chip.getAttribute("aria-controls")).toBe(passage.id);
  });

  it("closes on Escape and puts focus back on the mark that opened it", () => {
    render(
      <CitedAnswer
        sourceId="s1"
        text="Ada Lovelace wrote it.[^1]"
        citations={[first]}
      />,
    );
    const mark = screen.getByRole("button", { name: "Citation 1" });

    mark.focus();
    fireEvent.click(mark);
    expect(screen.getByTestId("citation-passage")).toBeTruthy();

    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(screen.queryByTestId("citation-passage")).toBeNull();
    expect(document.activeElement).toBe(mark);
    expect(mark.getAttribute("aria-expanded")).toBe("false");
  });

  it("keeps the Open note affordance for a note-origin citation", () => {
    render(
      <CitedAnswer
        sourceId="s1"
        text="My own note says so.[^1]"
        citations={[noteCitation]}
        onShowInBook={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Citation 1" }));

    expect(screen.getByText("Your note — My Insight")).toBeTruthy();
    const link = screen.getByRole("link", { name: /open note/i });
    expect(link.getAttribute("href")).toBe("/notes/note-123");
    // A note passage never offers an into-the-book action.
    expect(screen.queryByRole("button", { name: /show in book/i })).toBeNull();
  });

  it("renders the answer's own links as links, untouched by the mark treatment", () => {
    render(
      <CitedAnswer
        sourceId="s1"
        text="See [the archive](https://example.com/archive).[^1]"
        citations={[first]}
      />,
    );

    const link = screen.getByRole("link", { name: "the archive" });
    expect(link.getAttribute("href")).toBe("https://example.com/archive");
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeTruthy();
  });

  it("keeps a model-authored link sandboxed the way the renderer's own would be", () => {
    // The answer text is untrusted — the model wrote it from a book anyone can
    // upload — so overriding the renderer's anchor must not cost its hardening:
    // a new context, with no handle back on `window.opener`.
    render(
      <CitedAnswer
        sourceId="s1"
        text="Read [more](https://example.com/elsewhere) about it.[^1]"
        citations={[first]}
      />,
    );

    const link = screen.getByRole("link", { name: "more" });
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
