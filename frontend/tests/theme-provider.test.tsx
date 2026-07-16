// @vitest-environment jsdom

/**
 * A4 gate (component) — the theme provider applies the chosen theme as a class
 * on <html> and persists the choice so it survives a reload (FE-02).
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useTheme } from "next-themes";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "../app/components/theme-provider";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <button type="button" onClick={() => setTheme("dark")}>
      theme:{theme ?? "unset"}
    </button>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
  // next-themes reads the system preference on mount; jsdom has no matchMedia.
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
});

afterEach(cleanup);

describe("ThemeProvider", () => {
  it("applies the selected theme as a class on <html> and persists it", () => {
    render(
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <ThemeToggle />
      </ThemeProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByRole("button"));
    });

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("theme")).toBe("dark");
  });

  it("restores the persisted theme on a fresh mount", () => {
    window.localStorage.setItem("theme", "dark");

    render(
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <ThemeToggle />
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(screen.getByRole("button").textContent).toContain("dark");
  });
});
