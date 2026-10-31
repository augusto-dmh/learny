// @vitest-environment jsdom

/**
 * Data saver: the low-bandwidth budget. The resolution table (override beats
 * the browser's Save-Data signal beats off), the reader control that persists
 * the choice device-local, and the reader surface that stops requesting book
 * figures and shows the notice while it is active.
 */

import { cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { ChapterMarkdown } from "../app/components/chapter-markdown";
import { ReadingControls } from "../app/components/reading-controls";
import {
  DATA_SAVER_KEY,
  readDataSaverOverride,
  resolveDataSaver,
  systemSaveData,
  useDataSaver,
} from "../app/components/use-data-saver";

// ChapterFlow reads next/navigation and next-themes; stub both (mirrors
// reading-controls.test's container-integration harness).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "s1" }),
}));
vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "system",
    resolvedTheme: "light",
    setTheme: vi.fn(),
  }),
}));

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("resolution table", () => {
  it("an explicit choice wins, else the browser signal, else off", () => {
    expect(resolveDataSaver("on", false)).toBe(true);
    expect(resolveDataSaver("off", true)).toBe(false);
    expect(resolveDataSaver(null, true)).toBe(true);
    expect(resolveDataSaver(null, false)).toBe(false);
  });

  it("reads the stored override and ignores anything else", () => {
    const storage = (value: string | null) =>
      ({ getItem: () => value }) as unknown as Storage | null;
    expect(readDataSaverOverride(storage("on"))).toBe("on");
    expect(readDataSaverOverride(storage("off"))).toBe("off");
    expect(readDataSaverOverride(storage("zzz"))).toBeNull();
    expect(readDataSaverOverride(null)).toBeNull();
  });

  it("reads the browser Save-Data signal", () => {
    expect(systemSaveData({ saveData: true })).toBe(true);
    expect(systemSaveData({ saveData: false })).toBe(false);
    expect(systemSaveData(undefined)).toBe(false);
  });
});

describe("the hook", () => {
  it("persists the toggle and applies it immediately, and Off overrides Save-Data", async () => {
    Object.defineProperty(navigator, "connection", {
      value: { saveData: true },
      configurable: true,
    });

    const first = renderHook(() => useDataSaver());
    await waitFor(() => expect(first.result.current.system).toBe(true));
    expect(first.result.current.dataSaver).toBe(true);

    act(() => first.result.current.setOverride("off"));
    expect(first.result.current.dataSaver).toBe(false);
    expect(localStorage.getItem(DATA_SAVER_KEY)).toBe("off");

    // A fresh mount reads the persisted choice; Off still beats the signal.
    const second = renderHook(() => useDataSaver());
    await waitFor(() =>
      expect(second.result.current.override).toBe("off"),
    );
    expect(second.result.current.dataSaver).toBe(false);

    // Clearing the override returns to the browser signal.
    act(() => second.result.current.setOverride(null));
    expect(second.result.current.dataSaver).toBe(true);
    expect(localStorage.getItem(DATA_SAVER_KEY)).toBeNull();
  });
});

describe("the reader control", () => {
  it("toggling Data saver calls the setter and shows the browser note", () => {
    const onDataSaverChange = vi.fn();
    render(
      <ReadingControls
        size={19}
        leading={1.6}
        appearance="default"
        onSizeChange={vi.fn()}
        onLeadingChange={vi.fn()}
        onAppearanceChange={vi.fn()}
        dataSaver={false}
        dataSaverSystem={true}
        dataSaverOverride={null}
        onDataSaverChange={onDataSaverChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));

    const group = screen.getByTestId("data-saver-control");
    expect(group).not.toBeNull();
    fireEvent.click(withinGroup(group, "On"));
    expect(onDataSaverChange).toHaveBeenCalledWith("on");
    fireEvent.click(withinGroup(group, "Off"));
    expect(onDataSaverChange).toHaveBeenCalledWith("off");
    // The browser asked for less data and nothing overrides it yet.
    expect(screen.getByText("Your browser asked to save data.")).toBeTruthy();

    // Without a setter the control is absent (other consumers unaffected).
    cleanup();
    render(
      <ReadingControls
        size={19}
        leading={1.6}
        appearance="default"
        onSizeChange={vi.fn()}
        onLeadingChange={vi.fn()}
        onAppearanceChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reading settings" }));
    expect(screen.queryByTestId("data-saver-control")).toBeNull();
  });
});

describe("the reader surface", () => {
  const MEDIA_SRC =
    "/api/sources/0f0d1a2b-3c4d-5e6f-8a9b-0c1d2e3f4a5b/media/" +
    "a".repeat(64);

  it("hides book figures and shows the notice while data saver is active", async () => {
    const markdown = `Before.\n\n![Plate one](${MEDIA_SRC})\n\nAfter.`;

    const online = render(<ChapterMarkdown>{markdown}</ChapterMarkdown>);
    await waitFor(() =>
      expect(online.container.querySelector("img")).not.toBeNull(),
    );
    cleanup();

    const saver = render(
      <ChapterMarkdown dataSaver={true}>{markdown}</ChapterMarkdown>,
    );
    await waitFor(() => {
      // The sanitize pass strips the figure entirely: the browser never even
      // opens a media request.
      expect(saver.container.querySelector("img")).toBeNull();
    });
    expect(saver.container.textContent).toContain("Before.");
    expect(saver.container.textContent).toContain("After.");
  });

  it("the reader shows the notice under the browser's Save-Data signal", async () => {
    Object.defineProperty(navigator, "connection", {
      value: { saveData: true },
      configurable: true,
    });
    const chapter = {
      chapter_title: "Chapter One",
      chapter_anchor: "ch1#s1",
      chapter_index: 0,
      chapter_count: 1,
      prev_anchor: null,
      next_anchor: null,
      words_before_chapter: 0,
      chapter_word_count: 100,
      total_word_count: 100,
      words_per_page: 275,
      sections: [
        {
          anchor: "ch1#s1",
          title: "Opening",
          section_path: ["Chapter One"],
          markdown: `The opening.\n\n![Plate](${MEDIA_SRC})`,
          word_count: 100,
        },
      ],
      reading_position: null,
    };
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="c" chapter={chapter} scrollTarget={null} />,
    );
    expect(await screen.findByTestId("data-saver-notice")).toBeTruthy();
    await waitFor(() => expect(container.querySelector("img")).toBeNull());
  }, 15000);
});

function withinGroup(group: HTMLElement, name: string): HTMLElement {
  const buttons = Array.from(group.querySelectorAll("button"));
  const found = buttons.find((button) => button.textContent === name);
  if (!found) {
    throw new Error(`no ${name} in group`);
  }
  return found as HTMLElement;
}
