// @vitest-environment jsdom

/**
 * C3 (RD-06/22/23/25) — the in-reader table of contents and chapter nav. The TOC
 * marks the current section from live scroll state, scrolls in-flow for a
 * same-chapter click (no reload) while pushing to another chapter for a
 * cross-chapter click, and collapses behind the top-bar toggle below lg. Chapter
 * nav links to the adjacent chapters and is absent at a book edge.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { ChapterNav, TocPanel } from "../app/components/toc-panel";
import type { ChapterView } from "../app/lib/reading";
import type { SourceStructure } from "../app/lib/sources";

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
  nav.push.mockClear();
  nav.replace.mockClear();
});

const A = "part1/ch1.xhtml#s1";
const B = "part1/ch1.xhtml#s2";
const C = "part1/ch2.xhtml#s1";

/** A three-section book: A and B are chapter one, C is chapter two. */
const structure: SourceStructure = {
  title: "Book",
  authors: [],
  language: "en",
  sections: [
    { title: "S1", depth: 0, section_path: ["S1"], anchor: A, children: [] },
    { title: "S2", depth: 0, section_path: ["S2"], anchor: B, children: [] },
    { title: "S3", depth: 0, section_path: ["S3"], anchor: C, children: [] },
  ],
};

/** Render TocPanel with an injected structure fetch; returns the fetch spy + spies. */
function renderToc(overrides?: {
  currentAnchor?: string | null;
  chapterSectionAnchors?: string[];
}) {
  const fetchStructureImpl = vi.fn().mockResolvedValue(structure);
  const onSameChapterNavigate = vi.fn();
  const view = render(
    <TocPanel
      sourceId="s1"
      currentAnchor={overrides?.currentAnchor ?? A}
      chapterAnchor={A}
      chapterSectionAnchors={overrides?.chapterSectionAnchors ?? [A, B]}
      open={false}
      onSameChapterNavigate={onSameChapterNavigate}
      fetchStructureImpl={fetchStructureImpl}
    />,
  );
  return { view, fetchStructureImpl, onSameChapterNavigate };
}

describe("TocPanel position context (RD-22)", () => {
  it("marks the current section from scroll state and moves the mark as it changes", async () => {
    const { view } = renderToc({ currentAnchor: A });
    const s1 = await screen.findByRole("button", { name: "S1" });
    // The current section carries aria-current; a sibling does not.
    expect(s1.getAttribute("aria-current")).toBe("location");
    expect(screen.getByRole("button", { name: "S2" }).getAttribute("aria-current")).toBeNull();

    // Scroll moves the current section to B → the mark follows.
    view.rerender(
      <TocPanel
        sourceId="s1"
        currentAnchor={B}
        chapterAnchor={A}
        chapterSectionAnchors={[A, B]}
        open={false}
        onSameChapterNavigate={vi.fn()}
        fetchStructureImpl={vi.fn().mockResolvedValue(structure)}
      />,
    );
    expect(screen.getByRole("button", { name: "S2" }).getAttribute("aria-current")).toBe(
      "location",
    );
    expect(screen.getByRole("button", { name: "S1" }).getAttribute("aria-current")).toBeNull();
  });
});

describe("TocPanel navigation (RD-23)", () => {
  it("scrolls in-flow for a same-chapter click without reloading or re-fetching", async () => {
    const { fetchStructureImpl, onSameChapterNavigate } = renderToc({
      chapterSectionAnchors: [A, B],
    });
    fireEvent.click(await screen.findByRole("button", { name: "S2" }));

    // B is in the loaded chapter → in-flow scroll via the parent, no chapter load.
    expect(onSameChapterNavigate).toHaveBeenCalledWith(B);
    expect(nav.push).not.toHaveBeenCalled();
    // The structure was fetched once on mount and never again for the click.
    expect(fetchStructureImpl).toHaveBeenCalledTimes(1);
  });

  it("pushes the reader route for a cross-chapter click, encoding the anchor once", async () => {
    const { onSameChapterNavigate } = renderToc({ chapterSectionAnchors: [A, B] });
    fireEvent.click(await screen.findByRole("button", { name: "S3" }));

    // C is in another chapter → a new content round-trip, URL updated.
    expect(nav.push).toHaveBeenCalledWith(
      "/sources/s1/read?anchor=part1%2Fch2.xhtml%23s1",
    );
    expect(onSameChapterNavigate).not.toHaveBeenCalled();
  });
});

describe("TocPanel collapse (RD-25)", () => {
  it("reflects the open state so the panel can hide below lg and show when toggled", () => {
    const shared = {
      sourceId: "s1",
      currentAnchor: A,
      chapterAnchor: A,
      chapterSectionAnchors: [A, B],
      onSameChapterNavigate: vi.fn(),
      fetchStructureImpl: vi.fn().mockResolvedValue(structure),
    };
    const { rerender } = render(<TocPanel {...shared} open={false} />);
    const panel = screen.getByTestId("toc-panel");
    // Closed: hidden below lg (shown only at ≥lg via the lg:block utility).
    expect(panel.getAttribute("data-state")).toBe("closed");
    expect(panel.className).toContain("hidden");

    rerender(<TocPanel {...shared} open={true} />);
    expect(screen.getByTestId("toc-panel").getAttribute("data-state")).toBe("open");
    expect(screen.getByTestId("toc-panel").className).toContain("block");
  });

  it("toggles the panel open from the reader's top-bar control", async () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={chapterOne} scrollTarget={null} />);
    const toggle = screen.getByRole("button", { name: "Table of contents" });
    // Collapsed by default; the top-bar toggle opens it.
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("toc-panel").getAttribute("data-state")).toBe("closed");

    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("toc-panel").getAttribute("data-state")).toBe("open");
  });
});

describe("ChapterNav prev/next (RD-06)", () => {
  it("links to both adjacent chapters when they exist, encoding anchors once", () => {
    render(<ChapterNav sourceId="s1" prevAnchor={A} nextAnchor={C} />);
    expect(
      screen.getByRole("link", { name: /previous chapter/i }).getAttribute("href"),
    ).toBe("/sources/s1/read?anchor=part1%2Fch1.xhtml%23s1");
    expect(
      screen.getByRole("link", { name: /next chapter/i }).getAttribute("href"),
    ).toBe("/sources/s1/read?anchor=part1%2Fch2.xhtml%23s1");
  });

  it("omits the previous control at the first chapter", () => {
    render(<ChapterNav sourceId="s1" prevAnchor={null} nextAnchor={C} />);
    expect(screen.queryByRole("link", { name: /previous chapter/i })).toBeNull();
    expect(screen.getByRole("link", { name: /next chapter/i })).toBeTruthy();
  });

  it("renders nothing for a single-chapter book (no adjacent chapters)", () => {
    const { container } = render(
      <ChapterNav sourceId="s1" prevAnchor={null} nextAnchor={null} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

const chapterOne: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: A,
  chapter_index: 0,
  chapter_count: 2,
  prev_anchor: null,
  next_anchor: C,
  words_before_chapter: 0,
  chapter_word_count: 100,
  total_word_count: 200,
  sections: [
    { anchor: A, title: "S1", section_path: ["S1"], markdown: "First.", word_count: 60 },
    { anchor: B, title: "S2", section_path: ["S2"], markdown: "Second.", word_count: 40 },
  ],
  reading_position: null,
};
