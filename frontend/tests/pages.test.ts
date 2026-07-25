import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { countWords, pageAt, sectionOffsets } from "../app/lib/pages";

/**
 * The page unit's arithmetic, on its own.
 *
 * `pageAt` and `countWords` are what every page number and every page rule in the
 * reader is built from, and until now they were only ever exercised through a
 * rendered chapter — a component test can show that *some* rules landed, but not
 * that the number on one is the number the book would print.
 *
 * The boundary cases are not written here. They live in
 * `contracts/page-boundaries.json`, and the server's own implementation of the
 * same rule asserts the same file. That is the whole point: the two are separate
 * hand-written mirrors, so a table only one of them reads would let them drift
 * apart with both suites green.
 */

type BoundaryCase = {
  words_before: number;
  words_per_page: number;
  page: number;
  why: string;
};

const contract = JSON.parse(
  readFileSync(
    new URL("../../contracts/page-boundaries.json", import.meta.url),
    "utf8",
  ),
) as { cases: BoundaryCase[] };

describe("pageAt", () => {
  it("matches every shared boundary case", () => {
    // A contract nobody reads proves nothing: fail loudly if the file empties out.
    expect(contract.cases.length).toBeGreaterThanOrEqual(12);
    const actual = contract.cases.map((c) => ({
      words_before: c.words_before,
      words_per_page: c.words_per_page,
      page: pageAt(c.words_before, c.words_per_page),
    }));
    const expected = contract.cases.map((c) => ({
      words_before: c.words_before,
      words_per_page: c.words_per_page,
      page: c.page,
    }));
    expect(actual).toEqual(expected);
  });

  it("turns the page exactly on the quantum, never a word early or late", () => {
    // The same property the shared table pins, stated as a run rather than a list:
    // an off-by-one in either direction shows up as a shifted boundary here.
    const pages = Array.from({ length: 12 }, (_, i) => pageAt(i, 4));
    expect(pages).toEqual([1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]);
  });

  it("clamps a negative offset to the first page", () => {
    expect(pageAt(-1, 275)).toBe(1);
    expect(pageAt(-500, 275)).toBe(1);
  });

  it("reads page one for a non-positive quantum rather than dividing by it", () => {
    expect(pageAt(1000, 0)).toBe(1);
    expect(pageAt(1000, -275)).toBe(1);
  });
});

describe("sectionOffsets", () => {
  it("starts each section where the previous one ended", () => {
    const sections = [{ word_count: 300 }, { word_count: 50 }, { word_count: 120 }];
    expect(sectionOffsets(sections, 0)).toEqual([0, 300, 350]);
  });

  it("continues from the words before the chapter rather than from zero", () => {
    // This is what keeps page numbers book-global: chapter two's first section
    // does not start the count again.
    const sections = [{ word_count: 300 }, { word_count: 50 }];
    expect(sectionOffsets(sections, 5000)).toEqual([5000, 5300]);
  });

  it("gives a chapter's first section the chapter's own offset", () => {
    expect(sectionOffsets([{ word_count: 10 }], 275)).toEqual([275]);
    // ...which is the page the reader sees the chapter open on.
    expect(pageAt(sectionOffsets([{ word_count: 10 }], 275)[0], 275)).toBe(2);
  });

  it("carries a section with no words without swallowing the offset", () => {
    const sections = [{ word_count: 0 }, { word_count: 40 }, { word_count: 0 }];
    expect(sectionOffsets(sections, 100)).toEqual([100, 100, 140]);
  });

  it("has one entry per section, positionally", () => {
    expect(sectionOffsets([], 700)).toEqual([]);
    expect(sectionOffsets([{ word_count: 1 }, { word_count: 2 }], 0)).toHaveLength(2);
  });
});

describe("countWords", () => {
  it("counts whitespace-separated runs the way a reader would", () => {
    expect(countWords("one two three")).toBe(3);
  });

  it("does not count layout as words", () => {
    // Newlines, tabs and runs of spaces separate words; they are not words.
    expect(countWords("  one\ttwo\n\nthree  ")).toBe(3);
  });

  it("counts nothing in a blank block", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   \n\t ")).toBe(0);
  });

  it("counts a hyphenated or punctuated run as the one word it reads as", () => {
    expect(countWords("well-known, isn't it?")).toBe(3);
  });
});
