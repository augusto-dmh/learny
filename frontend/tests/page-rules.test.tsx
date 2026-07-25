// @vitest-environment jsdom

/**
 * B2 (PAGE-13/14) — the page unit made visible. The reader draws a rule at each
 * page boundary of the chapter, labelled with the page that starts below it.
 *
 * Three properties carry the requirement, and each has a test here: a rule lands
 * *between* the book's blocks and never inside a paragraph nor after the last
 * one; the running word count carries across boundaries instead of resetting;
 * and the numbers are the book's, continuing from the words before the chapter
 * rather than restarting per chapter. The quantum itself is the server's — the
 * reader renders whatever `words_per_page` the chapter response carries and
 * holds no words-per-page of its own.
 *
 * The rules are scaffolding, not prose: the highlight painter must read straight
 * past them, which the last test here is the sensor for.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { paginateSection } from "../app/lib/pages";
import type { ChapterView, SourceHighlightView } from "../app/lib/reading";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "s1" }),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", resolvedTheme: "light", setTheme: vi.fn() }),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

const S1 = "part1/ch1.xhtml#s1";
const S2 = "part1/ch1.xhtml#s2";

/** A paragraph of exactly ten distinguishable words. */
function paragraph(n: number): string {
  return [`Block${n}`, ...Array.from({ length: 9 }, () => `w${n}`)].join(" ");
}

/** Eight ten-word paragraphs — eighty words of prose to page. */
const EIGHT = Array.from({ length: 8 }, (_, i) => paragraph(i + 1)).join("\n\n");

/** A chapter whose single section holds `markdown`, at the given book offsets. */
function chapterOf({
  markdown = EIGHT,
  wordsPerPage = 25,
  wordsBeforeChapter = 0,
}: {
  markdown?: string;
  wordsPerPage?: number;
  wordsBeforeChapter?: number;
} = {}): ChapterView {
  return {
    chapter_title: "Chapter One",
    chapter_anchor: S1,
    chapter_index: 0,
    chapter_count: 1,
    prev_anchor: null,
    next_anchor: null,
    words_before_chapter: wordsBeforeChapter,
    chapter_word_count: 80,
    total_word_count: 1000,
    words_per_page: wordsPerPage,
    sections: [
      {
        anchor: S1,
        title: "Beginnings",
        section_path: ["Beginnings"],
        markdown,
        word_count: 80,
      },
    ],
    reading_position: null,
  };
}

/** The labels of the rendered page rules, in reading order. */
function ruleLabels(): string[] {
  return screen.queryAllByTestId("page-rule").map((rule) => rule.textContent ?? "");
}

/** The text of the paragraph immediately preceding each rendered rule. */
function textBeforeRules(): string[] {
  return screen.queryAllByTestId("page-rule").map((rule) => {
    // The rule closes a run of prose; the run before it ends with a paragraph.
    const paragraphs = (
      rule.previousElementSibling as HTMLElement
    ).querySelectorAll("p");
    return paragraphs[paragraphs.length - 1].textContent ?? "";
  });
}

describe("page rules in the reading column (PAGE-13)", () => {
  it("draws a rule at each page boundary, between paragraphs and never inside one", async () => {
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf()}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));

    // Rules exist, and none of them sits inside a paragraph.
    const rules = screen.getAllByTestId("page-rule");
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) {
      expect(rule.closest("p")).toBeNull();
    }
    // Every paragraph is whole: none was cut in half to make room for a rule.
    const rendered = Array.from(container.querySelectorAll(".book-prose p")).map(
      (p) => p.textContent,
    );
    expect(rendered).toEqual(Array.from({ length: 8 }, (_, i) => paragraph(i + 1)));
  });

  it("never rules off the end of the section", async () => {
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf()}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(8));

    // The final paragraph is followed by nothing: a rule there would be ruling
    // off the section, not marking a page turn inside it.
    const body = container.querySelector(".book-prose")!;
    expect(
      body.lastElementChild!.getAttribute("data-testid"),
    ).not.toBe("page-rule");
  });

  it("carries the remainder across boundaries instead of restarting the count", async () => {
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf()}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));

    // At 25 words a page and 10 words a paragraph, the boundaries fall at 25 and
    // 50 words — after the third and the fifth paragraph. A count that reset at
    // each rule would put the second boundary 25 words later, after the sixth.
    expect(textBeforeRules()).toEqual([
      paragraph(3),
      paragraph(5),
    ]);
  });

  it("hides the rules from assistive technology — they are furniture, not prose", async () => {
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf()}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));

    for (const rule of screen.getAllByTestId("page-rule")) {
      expect(rule.getAttribute("aria-hidden")).toBe("true");
    }
  });
});

describe("page numbers are the book's (PAGE-14)", () => {
  it("labels each rule with the page that starts below it", async () => {
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf()}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));

    expect(ruleLabels()).toEqual(["p. 2", "p. 3"]);
  });

  it("continues the book's numbering rather than restarting for the chapter", async () => {
    // A chapter that opens 100 words into the book opens on page 5 (at 25 words
    // a page), so its first rule is the turn onto page 6 — not page 2.
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf({ wordsBeforeChapter: 100 })}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));

    expect(ruleLabels()).toEqual(["p. 6", "p. 7"]);
  });

  it("pages by the quantum the server served, holding none of its own", async () => {
    // The same prose at a different served quantum pages differently: at 40
    // words a page the only boundary inside the section falls after the fourth
    // paragraph. A client carrying its own words-per-page could not do this.
    const { unmount } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf({ wordsPerPage: 40 })}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));
    expect(ruleLabels()).toEqual(["p. 2"]);
    expect(textBeforeRules()).toEqual([paragraph(4)]);
    unmount();

    // A quantum larger than the whole section yields no boundary at all.
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapterOf({ wordsPerPage: 10000 })}
        scrollTarget={null}
      />,
    );
    await screen.findByText(paragraph(1));
    expect(screen.queryAllByTestId("page-rule")).toHaveLength(0);
  });

  it("keeps numbering running across the chapter's sections", async () => {
    const chapter: ChapterView = {
      ...chapterOf(),
      chapter_word_count: 160,
      sections: [
        {
          anchor: S1,
          title: "Beginnings",
          section_path: ["Beginnings"],
          markdown: EIGHT,
          word_count: 80,
        },
        {
          anchor: S2,
          title: "Mechanism",
          section_path: ["Mechanism"],
          markdown: Array.from({ length: 8 }, (_, i) => paragraph(i + 11)).join(
            "\n\n",
          ),
          word_count: 80,
        },
      ],
    };
    render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText(paragraph(11));

    // The second section starts 80 words in, on page 4; its own boundaries
    // follow from there rather than starting the count again — so it opens with
    // the turn onto page 5, not another page 2.
    expect(ruleLabels()).toEqual(["p. 2", "p. 3", "p. 5", "p. 6", "p. 7"]);
  });
});

describe("blocks a rule must not cut (PAGE-13)", () => {
  const wordsPerPage = 25;

  it("defers a boundary that falls on a list or a heading to the next paragraph", () => {
    const markdown = [
      paragraph(1),
      paragraph(2),
      "- one item\n- two item\n- three item",
      "## A heading here",
      paragraph(3),
      paragraph(4),
    ].join("\n\n");

    const runs = paginateSection(markdown, { wordsBefore: 0, wordsPerPage });

    // The boundary falls on the list, which a rule would cut in half; it waits
    // for the next paragraph and takes its number from where the count then is.
    const breaks = runs.filter((run) => run.pageAfter !== null);
    expect(breaks).toHaveLength(1);
    expect(breaks[0].markdown.trimEnd().endsWith(paragraph(3))).toBe(true);
    expect(breaks[0].pageAfter).toBe(2);
  });

  it("never breaks inside a fenced code block", () => {
    const code = ["```", ...Array.from({ length: 30 }, (_, i) => `line ${i}`), "```"].join(
      "\n",
    );
    const markdown = [paragraph(1), code, paragraph(2), paragraph(3)].join("\n\n");

    const runs = paginateSection(markdown, { wordsBefore: 0, wordsPerPage });

    for (const run of runs) {
      // A fence that opened in a run also closes in it.
      expect((run.markdown.match(/```/g) ?? []).length % 2).toBe(0);
    }
  });

  it("leaves a section with no boundary in it exactly as it was served", () => {
    const markdown = `${paragraph(1)}\n\n${paragraph(2)}`;
    expect(paginateSection(markdown, { wordsBefore: 0, wordsPerPage: 275 })).toEqual([
      { markdown, pageAfter: null },
    ]);
  });
});

describe("rules are invisible to the highlight painter (PAGE-13)", () => {
  it("paints a highlight on the occurrence its context names, across a rule", async () => {
    // The quote appears twice; only the captured context tells the two apart,
    // and that context runs straight through a page rule. If the rule's own
    // label counted as book text, the context would no longer match and the
    // highlight would land on the wrong words — or on none.
    const paragraphs = [
      "Ada studied the machine closely.",
      "Then the engine turns and stops.",
      "Babbage checked every brass wheel.",
      "Later the engine turns again.",
      "The room fell quiet afterwards.",
    ];
    const chapter: ChapterView = {
      ...chapterOf({ markdown: paragraphs.join("\n\n"), wordsPerPage: 16 }),
      chapter_word_count: 26,
    };
    const highlight: SourceHighlightView = {
      note_id: "n1",
      note_title: "the engine turns",
      has_body: false,
      anchor: S1,
      quote_exact: "the engine turns",
      quote_prefix: "wheel.Later ",
      quote_suffix: " again.",
      status: "active",
    };

    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="c"
        chapter={chapter}
        scrollTarget={null}
        highlights={[highlight]}
      />,
    );
    await screen.findByText(paragraphs[0]);
    // The rule the context reads across is really there.
    expect(screen.getAllByTestId("page-rule")).toHaveLength(1);

    await waitFor(() =>
      expect(container.querySelectorAll("mark.reader-highlight")).toHaveLength(1),
    );
    const mark = container.querySelector("mark.reader-highlight")!;
    expect(mark.textContent).toBe("the engine turns");
    // On the fourth paragraph — the one the context pointed at — not the second.
    expect(mark.closest("p")!.textContent).toBe(paragraphs[3]);
  });
});
