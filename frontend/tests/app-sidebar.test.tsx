// @vitest-environment jsdom

/**
 * C gate (component) — the app navigation sidebar (HOME-16). The nav collapses
 * to exactly four primary destinations — Home, Bookshelf, Review, Notes — with
 * the per-source book list removed; the brand link returns to Home. The book
 * list itself now lives on the Bookshelf and is covered by
 * tests/sources-screen.test.tsx and tests/library-screen.test.tsx.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AppSidebar } from "../app/components/shell/app-sidebar";
import { SidebarProvider } from "../components/ui/sidebar";

function renderSidebar() {
  return render(
    <SidebarProvider>
      <AppSidebar />
    </SidebarProvider>,
  );
}

beforeEach(() => {
  // shadcn SidebarProvider reads the viewport via matchMedia, absent in jsdom;
  // stub it to a stable (desktop) match.
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

afterEach(() => {
  cleanup();
});

describe("AppSidebar (HOME-16)", () => {
  it("shows exactly the four primary nav destinations with their routes", () => {
    renderSidebar();

    const nav = [
      { name: "Home", href: "/home" },
      { name: "Bookshelf", href: "/sources" },
      { name: "Review", href: "/review" },
      { name: "Notes", href: "/notes" },
    ];
    for (const { name, href } of nav) {
      expect(
        screen.getByRole("link", { name }).getAttribute("href"),
      ).toBe(href);
    }
  });

  it("presents the four nav items in order and nothing else in the menu", () => {
    const { container } = renderSidebar();

    // The menu list holds one link per destination, in the spec order.
    const menu = container.querySelector<HTMLElement>("[data-sidebar='menu']");
    expect(menu).not.toBeNull();
    const labels = within(menu!)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(labels).toEqual(["Home", "Bookshelf", "Review", "Notes"]);
  });

  it("points the brand link at Home", () => {
    renderSidebar();

    expect(
      screen.getByRole("link", { name: "Learny" }).getAttribute("href"),
    ).toBe("/home");
  });

  it("does not render a per-source Library group", () => {
    renderSidebar();

    expect(screen.queryByText("Library")).toBeNull();
  });
});
