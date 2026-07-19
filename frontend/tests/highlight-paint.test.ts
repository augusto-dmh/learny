// @vitest-environment jsdom

/**
 * D1 (RD-29, matching half) — `findQuoteOffset` locates a captured quote in the
 * served text, disambiguating repeats by prefix/suffix context, and returns
 * `null` rather than guess when the quote is absent or stays ambiguous. The
 * jsdom environment is shared with the D2 `paintHighlights` DOM tests below;
 * `findQuoteOffset` is pure string logic and behaves identically either way.
 */

import { describe, expect, it } from "vitest";

import {
  findQuoteOffset,
  paintHighlights,
  type PaintableHighlight,
} from "../app/lib/highlight-paint";

// "ref" occurs twice: at index 6 and index 15.
const REPEATED = "alpha ref beta ref gamma";

describe("findQuoteOffset (RD-29)", () => {
  it("returns the offset of a unique occurrence without needing context", () => {
    const haystack = "Ada Lovelace wrote the first algorithm.";
    expect(findQuoteOffset(haystack, "first algorithm", "", "")).toBe(23);
  });

  it("disambiguates a repeated quote by prefix and suffix context", () => {
    // Only the second "ref" is preceded by "beta " and followed by " gamma".
    expect(findQuoteOffset(REPEATED, "ref", "beta ", " gamma")).toBe(15);
  });

  it("disambiguates a repeated quote to the occurrence at the string start", () => {
    // "ref" at index 0 and 6; the suffix " x" only follows the first.
    expect(findQuoteOffset("ref x ref", "ref", "", " x")).toBe(0);
  });

  it("returns null for a repeated quote the context cannot narrow to one", () => {
    // Both occurrences are equally consistent with empty context: ambiguous.
    expect(findQuoteOffset(REPEATED, "ref", "", "")).toBeNull();
  });

  it("returns null when the quote does not occur at all", () => {
    expect(findQuoteOffset("hello world", "absent", "", "")).toBeNull();
  });

  it("returns null for an empty quote", () => {
    expect(findQuoteOffset("hello world", "", "", "")).toBeNull();
  });

  it("locates a unique quote sitting at the very end of the text", () => {
    const haystack = "the analytical engine";
    expect(findQuoteOffset(haystack, "engine", "analytical ", "")).toBe(15);
  });

  it("resolves a unique quote even when its stored context is empty", () => {
    // A quote captured at a section edge carries an empty prefix; a single
    // occurrence still resolves.
    expect(findQuoteOffset("ref then more", "ref", "", " then")).toBe(0);
  });
});

/** Build a detached element with the given inner HTML for painting. */
function root(html: string): HTMLElement {
  const el = document.createElement("div");
  el.innerHTML = html;
  return el;
}

const active = (over: Partial<PaintableHighlight>): PaintableHighlight => ({
  note_id: "n1",
  quote_exact: "",
  quote_prefix: "",
  quote_suffix: "",
  status: "active",
  ...over,
});

function marks(el: HTMLElement): HTMLElement[] {
  return Array.from(el.querySelectorAll<HTMLElement>("mark.reader-highlight"));
}

describe("paintHighlights (RD-28/29)", () => {
  it("wraps a matched active quote in a marker carrying its note id", () => {
    const el = root("<p>Babbage designed the analytical engine.</p>");
    paintHighlights(el, [active({ note_id: "n7", quote_exact: "designed the analytical engine" })]);

    const painted = marks(el);
    expect(painted).toHaveLength(1);
    expect(painted[0].textContent).toBe("designed the analytical engine");
    expect(painted[0].getAttribute("data-note-id")).toBe("n7");
  });

  it("paints one slice per text node when the quote spans inline formatting", () => {
    const el = root("<p>Ada <strong>Lovelace</strong> wrote the algorithm.</p>");
    paintHighlights(el, [
      active({ note_id: "n2", quote_exact: "Lovelace wrote", quote_prefix: "Ada ", quote_suffix: " the" }),
    ]);

    const painted = marks(el);
    // One mark inside <strong> for "Lovelace", one in the paragraph for " wrote".
    expect(painted).toHaveLength(2);
    expect(painted.every((m) => m.getAttribute("data-note-id") === "n2")).toBe(true);
    expect(painted.map((m) => m.textContent).join("")).toBe("Lovelace wrote");
    // The inline element the quote crossed is preserved.
    expect(el.querySelector("strong")?.textContent).toContain("Lovelace");
  });

  it("never paints a stale or orphaned highlight even when its quote is present", () => {
    const el = root("<p>Babbage designed the analytical engine.</p>");
    paintHighlights(el, [
      active({ quote_exact: "analytical engine", status: "stale" }),
      active({ quote_exact: "analytical engine", status: "orphaned" }),
    ]);

    expect(marks(el)).toHaveLength(0);
  });

  it("paints nothing, and does not throw, when the quote is absent", () => {
    const el = root("<p>Babbage designed the analytical engine.</p>");
    paintHighlights(el, [active({ quote_exact: "a phrase not in the prose" })]);

    expect(marks(el)).toHaveLength(0);
  });

  it("is idempotent: repainting the same highlights does not duplicate marks", () => {
    const el = root("<p>Babbage designed the analytical engine.</p>");
    const highlights = [active({ quote_exact: "analytical engine" })];

    paintHighlights(el, highlights);
    paintHighlights(el, highlights);

    const painted = marks(el);
    expect(painted).toHaveLength(1);
    expect(painted[0].textContent).toBe("analytical engine");
  });

  it("leaves the prose text unchanged — marks only wrap, so copy/select is intact", () => {
    const el = root("<p>Ada <strong>Lovelace</strong> wrote the algorithm.</p>");
    const before = el.textContent;

    paintHighlights(el, [active({ quote_exact: "Lovelace wrote", quote_prefix: "Ada ", quote_suffix: " the" })]);

    // No characters added or removed; the visible/selectable text is identical.
    expect(el.textContent).toBe(before);
  });
});
