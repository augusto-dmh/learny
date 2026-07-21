// @vitest-environment jsdom

/**
 * POL-11 — the ink-line header rule on the four top-level screens: Home,
 * Bookshelf, Review, and Notes each carry the static signature rule (no fill —
 * fills exist only where they encode real progress). The screens' data
 * behavior is covered by their own suites; every fetch here fails so only the
 * header framing is under test.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import HomePage from "../app/(app)/home/page";
import NotesPage from "../app/(app)/notes/page";
import ReviewPage from "../app/(app)/review/page";
import SourcesPage from "../app/(app)/sources/page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe.each([
  ["Home", HomePage, "Home"],
  ["Bookshelf", SourcesPage, "Your bookshelf"],
  ["Review", ReviewPage, "Review"],
  ["Notes", NotesPage, "Notes"],
] as const)("%s screen header", (_name, Page, title) => {
  it(`rules the "${title}" heading with a fill-free ink-line`, () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );

    render(<Page />);

    const heading = screen.getByRole("heading", { level: 1, name: title });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    const rule = header!.querySelector('[data-testid="ink-line"]');
    expect(rule).not.toBeNull();
    expect(rule!.querySelector('[data-testid="ink-line-fill"]')).toBeNull();
  });
});
