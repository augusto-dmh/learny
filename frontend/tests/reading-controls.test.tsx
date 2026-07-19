// @vitest-environment jsdom

/**
 * C2 (RD-17/19/20/21) — the `Aa` reading-controls popover. It offers the four
 * axes (size, spacing, appearance, theme); selecting a step calls the matching
 * setter (settings) or next-themes `setTheme` (theme). Selecting Paper sets
 * `data-appearance="paper"` on the reader container only — never the chrome — and
 * under a dark theme both the `.dark` class and the Paper attribute coexist while
 * the popover keeps the appearance axis visible with its night-palette note
 * (ADR-027 / AD-119: dark stays authoritative, the guarded selector is inert).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { ReadingControls } from "../app/components/reading-controls";
import type { ChapterView } from "../app/lib/reading";

// next-themes is mocked with a controllable theme so the dark-mode branch and
// the `setTheme` calls are observable without a real provider.
const theme = vi.hoisted(() => ({
  current: "system",
  resolved: "light",
  setTheme: vi.fn(),
}));
vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: theme.current,
    resolvedTheme: theme.resolved,
    setTheme: theme.setTheme,
  }),
}));

// ChapterFlow reads next/navigation; stub it for the container-integration tests.
const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "s1" }),
}));

// Radix Popover reaches for ResizeObserver and the pointer-capture APIs jsdom
// lacks; stub them so the popover can open under test (mirrors citations.test).
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
  localStorage.clear();
  theme.current = "system";
  theme.resolved = "light";
  vi.clearAllMocks();
});

const chapter: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: "ch1#s1",
  chapter_index: 0,
  chapter_count: 1,
  prev_anchor: null,
  next_anchor: null,
  words_before_chapter: 0,
  chapter_word_count: 100,
  total_word_count: 100,
  sections: [
    {
      anchor: "ch1#s1",
      title: "Opening",
      section_path: ["Chapter One"],
      markdown: "The opening paragraph.",
      word_count: 100,
    },
  ],
  reading_position: null,
};

/** Render the controls with spy setters and open the popover. */
function renderControls() {
  const onSizeChange = vi.fn();
  const onLeadingChange = vi.fn();
  const onAppearanceChange = vi.fn();
  render(
    <ReadingControls
      size={19}
      leading={1.6}
      appearance="default"
      onSizeChange={onSizeChange}
      onLeadingChange={onLeadingChange}
      onAppearanceChange={onAppearanceChange}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
  return { onSizeChange, onLeadingChange, onAppearanceChange };
}

describe("ReadingControls axes (RD-17)", () => {
  it("selecting a type-size step calls the size setter with that step", () => {
    const { onSizeChange } = renderControls();
    fireEvent.click(screen.getByRole("button", { name: "Type size 23" }));
    expect(onSizeChange).toHaveBeenCalledWith(23);
  });

  it("selecting a line-spacing step calls the spacing setter with that step", () => {
    const { onLeadingChange } = renderControls();
    fireEvent.click(screen.getByRole("button", { name: "Line spacing 1.8" }));
    expect(onLeadingChange).toHaveBeenCalledWith(1.8);
  });

  it("selecting Paper calls the appearance setter with 'paper'", () => {
    const { onAppearanceChange } = renderControls();
    fireEvent.click(screen.getByRole("button", { name: "Paper" }));
    expect(onAppearanceChange).toHaveBeenCalledWith("paper");
  });

  it("selecting a theme calls next-themes setTheme with that value", () => {
    renderControls();
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(theme.setTheme).toHaveBeenCalledWith("dark");
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    expect(theme.setTheme).toHaveBeenCalledWith("system");
  });

  it("marks the current step as pressed on each axis", () => {
    renderControls();
    expect(
      screen.getByRole("button", { name: "Type size 19" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "Line spacing 1.6" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });
});

describe("ReadingControls appearance under dark (RD-20)", () => {
  it("keeps the appearance axis visible with a night-palette note under dark", () => {
    theme.resolved = "dark";
    renderControls();
    // The control is never hidden — both appearance steps stay clickable...
    expect(screen.getByRole("button", { name: "Default" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Paper" })).toBeTruthy();
    // ...and the popover explains the axis is inert under dark.
    expect(screen.getByText(/night palette/i)).toBeTruthy();
  });

  it("shows no night-palette note under a light theme", () => {
    theme.resolved = "light";
    renderControls();
    expect(screen.queryByText(/night palette/i)).toBeNull();
  });
});

describe("Paper appearance on the reader container (RD-19/20)", () => {
  it("sets data-appearance='paper' on the reading container only, not the chrome", () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Paper" }));

    // The reader surface carries the attribute; the sticky chrome does not — so
    // the Paper token layer cannot cascade into the top bar (chrome stays Iron Gall).
    const article = container.querySelector(".prose-reading")!;
    expect(article.getAttribute("data-appearance")).toBe("paper");
    expect(screen.getByTestId("reader-top-bar").hasAttribute("data-appearance")).toBe(
      false,
    );
  });

  it("leaves the .dark class authoritative when dark and Paper both apply", () => {
    theme.resolved = "dark";
    document.documentElement.classList.add("dark");
    try {
      const { container } = render(
        <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
      );
      const popover = within(document.body);
      fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
      fireEvent.click(popover.getByRole("button", { name: "Paper" }));

      // Both DOM states coexist: the reader records the Paper choice, but the
      // .dark class is still on <html>, so the guarded `html:not(.dark)` Paper
      // selector never matches — dark's night palette stays authoritative.
      expect(container.querySelector(".prose-reading")!.getAttribute("data-appearance")).toBe(
        "paper",
      );
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    } finally {
      document.documentElement.classList.remove("dark");
    }
  });
});
