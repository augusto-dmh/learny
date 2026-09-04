// @vitest-environment jsdom

/**
 * B1 (PAGE-11/12) — the reading column. The book gets a column with a real
 * measure, paragraph rhythm, a running chapter title, and foot room under the
 * last paragraph, on the warm paper surface when the reader asks for it. The
 * column spec is expressed *through* the Aa controls' `--reading-size` /
 * `--reading-leading` variables, never as fixed values over them (AD-186), so
 * the type-size and line-spacing steps the reader picks stay authoritative.
 *
 * jsdom applies no external stylesheet, so the column's own values are verified
 * the way the palette is (tests/theme-tokens.test.ts): by reading the committed
 * source. What the DOM can answer — which element wears which surface, and
 * whether the reader's choice still reaches the prose — is asserted by
 * rendering.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import type { ChapterView } from "../app/lib/reading";

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => nav.params,
  useParams: () => ({ id: "s1" }),
}));

vi.mock("../app/components/ask-panel", () => ({
  AskPanel: () => <div data-testid="ask-panel-body" />,
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: () => <div data-testid="teach-panel-body" />,
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", resolvedTheme: "light", setTheme: vi.fn() }),
}));

// Radix Popover reaches for ResizeObserver and pointer capture, which jsdom
// lacks; stub them so the Aa popover can open (mirrors reading-controls.test).
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

beforeEach(() => {
  nav.params = new URLSearchParams();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

// Read from the project root: under jsdom `import.meta.url` is an http URL, so
// the committed stylesheet is located from the runner's working directory.
const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

/** The declarations inside the first `selector { ... }` block in globals.css. */
function rule(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `rule "${selector}" exists`).toBeGreaterThanOrEqual(0);
  return css.slice(start + selector.length, css.indexOf("}", start));
}

/** The value of `property: value;` inside a block body. */
function declaration(block: string, property: string): string {
  const match = block.match(new RegExp(`(?:^|[;{\\s])${property}:\\s*([^;]+);`));
  expect(match, `declaration ${property} present`).not.toBeNull();
  return (match as RegExpMatchArray)[1].trim();
}

const S1 = "part1/ch1.xhtml#s1";
const S2 = "part1/ch1.xhtml#s2";

const chapter: ChapterView = {
  chapter_title: "The Analytical Engine",
  chapter_anchor: S1,
  chapter_index: 0,
  chapter_count: 1,
  prev_anchor: null,
  next_anchor: null,
  words_before_chapter: 0,
  chapter_word_count: 200,
  total_word_count: 400,
  words_per_page: 275,
  sections: [
    {
      anchor: S1,
      title: "Beginnings",
      section_path: ["Beginnings"],
      markdown: "First paragraph here.\n\nSecond paragraph here.",
      word_count: 100,
    },
    {
      anchor: S2,
      title: "Mechanism",
      section_path: ["Mechanism"],
      markdown: "Third paragraph here.",
      word_count: 100,
    },
  ],
  reading_position: null,
};

describe("the book column (PAGE-11)", () => {
  it("sets the column on one measure with paragraph rhythm and foot room", () => {
    // A measure a person can read a line of, not the full window width.
    expect(declaration(rule(".prose-reading"), "max-width")).toBe("65ch");
    // Paragraphs are separated, and in `em` so the rhythm follows the reader's
    // chosen type size instead of fighting it.
    expect(declaration(rule(".book-prose p"), "margin")).toBe("0 0 1.15em");
    // Room under the last paragraph so it never sits on the viewport floor.
    expect(declaration(rule(".book-column"), "padding")).toBe("40px 32px 200px");
  });

  it("gives the chapter a quiet running title in the book's own serif", () => {
    const title = rule(".chapter-running-title");
    expect(declaration(title, "font-family")).toBe("var(--font-serif)");
    expect(declaration(title, "text-transform")).toBe("uppercase");
    // Muted, so it labels the column rather than competing with the prose.
    expect(declaration(title, "color")).toBe("var(--muted-foreground)");
  });

  it("renders the chapter title at the head of the reading column", () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );

    const column = container.querySelector(".prose-reading")!;
    const title = screen.getByTestId("reading-chapter-title");
    expect(title.textContent).toBe("The Analytical Engine");
    // It heads the column itself — the sticky bar's copy recedes on scroll, so
    // the column keeps its own marker of where the chapter starts.
    expect(column.contains(title)).toBe(true);
    expect(column.firstElementChild).toBe(title);
  });

  it("keeps the warm paper surface on the reading column only", () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Paper" }));

    expect(
      container.querySelector(".prose-reading")!.getAttribute("data-appearance"),
    ).toBe("paper");
    expect(
      screen.getByTestId("reader-top-bar").hasAttribute("data-appearance"),
    ).toBe(false);
  });
});

describe("the Aa controls stay authoritative (PAGE-12)", () => {
  it("hands the reader's chosen type size and spacing to the column", () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );
    const column = container.querySelector<HTMLElement>(".prose-reading")!;

    fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Type size 23" }));
    fireEvent.click(screen.getByRole("button", { name: "Line spacing 1.8" }));

    // The column renders at the reader's steps — the approved column spec never
    // pins the size or the leading over the reader's choice.
    expect(column.style.getPropertyValue("--reading-size")).toBe("23px");
    expect(column.style.getPropertyValue("--reading-leading")).toBe("1.8");
  });

  it("reads its type size and line height from the reading variables", () => {
    const prose = rule(".prose-reading");
    expect(declaration(prose, "font-size")).toContain("var(--reading-size");
    expect(declaration(prose, "line-height")).toContain("var(--reading-leading");
    // The column spec's own type figures are never pinned into the stylesheet:
    // they would silently disable the size and spacing steps.
    expect(css).not.toContain("18.5px");
    expect(rule(".book-column")).not.toContain("font-size");
    expect(rule(".book-column")).not.toContain("line-height");
  });
});

describe("the open dock overlays below xl without shrinking the measure", () => {
  it("keeps computed .prose-reading max-width at 65ch when the dock is open", () => {
    nav.params = new URLSearchParams("panel=ask");
    const sheet = document.createElement("style");
    sheet.textContent = ".prose-reading { max-width: 65ch; }";
    document.head.appendChild(sheet);

    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );

    const prose = container.querySelector<HTMLElement>(".prose-reading")!;
    expect(getComputedStyle(prose).maxWidth).toBe("65ch");
    const panel = screen.getByTestId("reader-panel");
    const classes = panel.className.split(/\s+/);
    expect(classes).toContain("max-xl:fixed");
    expect(classes).toContain("max-xl:inset-y-0");
    expect(classes).toContain("max-xl:right-0");
    expect(classes).not.toContain("shrink-0");
    expect(classes).toContain("xl:shrink-0");
    expect(declaration(rule(".prose-reading"), "max-width")).toBe("65ch");
    sheet.remove();
  });
});
