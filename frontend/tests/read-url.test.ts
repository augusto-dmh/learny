/**
 * Unit — `readUrl` is the single home for the reader-route URL contract shared by
 * the TOC/chapter navigation, the citation "open in book" link, and the saved-note
 * jump-back. It emits the bare route with no query, adds an independent `anchor`
 * and/or `panel` query param, and percent-encodes the anchor exactly once (so a
 * reserved `/` or `#` in an anchor survives a round-trip through the query).
 */

import { describe, expect, it } from "vitest";

import { readUrl } from "../app/lib/read-url";

describe("readUrl", () => {
  it("emits the bare reader route with no anchor and no panel", () => {
    expect(readUrl("s1", null)).toBe("/sources/s1/read");
  });

  it("adds only the panel param when there is no anchor", () => {
    expect(readUrl("s1", null, { panel: "ask" })).toBe(
      "/sources/s1/read?panel=ask",
    );
  });

  it("adds only the anchor param when there is no panel", () => {
    expect(readUrl("s1", "c1")).toBe("/sources/s1/read?anchor=c1");
  });

  it("adds both params, anchor before panel", () => {
    expect(readUrl("s1", "c1", { panel: "teach" })).toBe(
      "/sources/s1/read?anchor=c1&panel=teach",
    );
  });

  it("percent-encodes an anchor's reserved / and # exactly once", () => {
    const anchor = "part1/ch1.xhtml#core-idea";
    const url = readUrl("s1", anchor);
    expect(url).toBe("/sources/s1/read?anchor=part1%2Fch1.xhtml%23core-idea");
    // Encoded exactly once: no double-encoded escapes, and decoding restores it.
    expect(url).not.toContain("%252F");
    expect(url).not.toContain("%2523");
    expect(decodeURIComponent(url.split("anchor=")[1])).toBe(anchor);
  });
});
