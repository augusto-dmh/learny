// @vitest-environment jsdom

/**
 * C4 (RD-24/30/31) — the reader's minimal chrome. The top bar recedes on
 * downward scroll and restores on upward scroll (`useRecedingChrome`), the
 * ink-line hairline fills proportional to whole-book percent and stays while the
 * bar recedes, and a return chip appears when a deep link opens away from the
 * stored reading position, brings the reader back on click, and dismisses itself
 * once the reader has scrolled well past the jump.
 */

import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { useRecedingChrome } from "../app/components/use-receding-chrome";
import type { ChapterView } from "../app/lib/reading";

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

const S1 = "part1/ch1.xhtml#s1";
const S2 = "part1/ch1.xhtml#s2";

const chapter: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: S1,
  chapter_index: 0,
  chapter_count: 1,
  prev_anchor: null,
  next_anchor: null,
  words_before_chapter: 100,
  chapter_word_count: 500,
  total_word_count: 1000,
  sections: [
    { anchor: S1, title: "One", section_path: ["One"], markdown: "First.", word_count: 300 },
    { anchor: S2, title: "Two", section_path: ["Two"], markdown: "Second.", word_count: 200 },
  ],
  reading_position: null,
};

/** Fire a scroll event whose target reports the given scrollTop (capture-phase). */
function scrollTo(el: HTMLElement, top: number) {
  Object.defineProperty(el, "scrollTop", { value: top, configurable: true });
  act(() => {
    fireEvent.scroll(el);
  });
}

describe("useRecedingChrome (RD-31)", () => {
  it("hides on downward scroll and restores on upward scroll", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const { result } = renderHook(() => useRecedingChrome(8));

    // Resting at the top: visible.
    expect(result.current).toBe(false);
    // Scrolling down past the threshold recedes the chrome...
    scrollTo(el, 200);
    expect(result.current).toBe(true);
    // ...and scrolling back up restores it.
    scrollTo(el, 40);
    expect(result.current).toBe(false);

    el.remove();
  });

  it("ignores sub-threshold jitter", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const { result } = renderHook(() => useRecedingChrome(8));

    scrollTo(el, 4); // below the 8px threshold
    expect(result.current).toBe(false);

    el.remove();
  });
});

describe("ink-line progress (RD-30)", () => {
  it("fills the hairline proportional to whole-book percent using tokens", () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />);
    // words_before 100 / total 1000 = 10% at the chapter top.
    const fill = screen.getByTestId("ink-line-fill");
    expect(fill.style.width).toBe("10%");
    // The fill is drawn from an identity token, never a raw colour.
    expect(fill.className).toContain("bg-primary");
  });

  it("keeps the ink-line mounted regardless of the receding bar", () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />);
    const el = screen.getByTestId("ink-line");
    scrollTo(el, 300); // recede the chrome
    // The rule stays even as the bar recedes (it is a sibling, never translated).
    expect(screen.getByTestId("ink-line")).toBeTruthy();
  });

  it("guards the chrome transform with motion-reduce so reduced motion does not animate", () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />);
    expect(screen.getByTestId("reader-top-bar").className).toContain(
      "motion-reduce:transition-none",
    );
  });
});

describe("return chip lifecycle (RD-24)", () => {
  const resumed: ChapterView = {
    ...chapter,
    reading_position: { anchor: S1, percent: 10, updated_at: "now" },
  };

  it("appears when a deep link opens away from the stored reading position", () => {
    // Stored position S1, deep-linked to S2 → the reader jumped away.
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={resumed} scrollTarget={S2} />);
    expect(screen.getByRole("button", { name: /return to where you were/i })).toBeTruthy();
  });

  it("stays hidden when the deep link lands on the stored position", () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={resumed} scrollTarget={S1} />);
    expect(screen.queryByRole("button", { name: /return to where you were/i })).toBeNull();
  });

  it("returns to the pre-jump position and dismisses on click", () => {
    render(<ChapterFlow sourceId="s1" csrf="c" chapter={resumed} scrollTarget={S2} />);
    const chip = screen.getByRole("button", { name: /return to where you were/i });
    fireEvent.click(chip);

    // Returned in-flow to the stored anchor (present in this chapter) and the
    // URL was replaced to it; the chip is gone.
    expect(nav.replace).toHaveBeenCalledWith(
      "/sources/s1/read?anchor=part1%2Fch1.xhtml%23s1",
    );
    expect(
      screen.queryByRole("button", { name: /return to where you were/i }),
    ).toBeNull();
  });

  it("dismisses once the reader has scrolled well past the jump", () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={resumed} scrollTarget={S2} />,
    );
    expect(screen.getByRole("button", { name: /return to where you were/i })).toBeTruthy();

    const article = container.querySelector(".prose-reading") as HTMLElement;
    scrollTo(article, 0); // baseline
    scrollTo(article, 600); // well past the 400px threshold
    expect(
      screen.queryByRole("button", { name: /return to where you were/i }),
    ).toBeNull();
  });
});
