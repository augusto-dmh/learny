// @vitest-environment jsdom

/**
 * D1 (RD-29, matching half) — `findQuoteOffset` locates a captured quote in the
 * served text, disambiguating repeats by prefix/suffix context, and returns
 * `null` rather than guess when the quote is absent or stays ambiguous. The
 * jsdom environment is shared with the D2 `paintHighlights` DOM tests below;
 * `findQuoteOffset` is pure string logic and behaves identically either way.
 */

import { describe, expect, it } from "vitest";

import { findQuoteOffset } from "../app/lib/highlight-paint";

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
