// @vitest-environment jsdom

/**
 * `/sources/{id}/read` route composition (READ-16/21): the page lives in the
 * `(read)` group, so AppSidebar and AuthHeader are absent from the document
 * rather than CSS-hidden. The column fills the viewport with no 3rem header
 * offset. A test that mounted this page inside the app shell would fail these
 * assertions.
 */

import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReadLayout from "../app/(read)/layout";
import ReadPage from "../app/(read)/sources/[id]/read/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useParams: () => ({ id: "s1" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/app/components/chapter-reader", () => ({
  ChapterReader: () => <div data-testid="chapter-reader">Chapter</div>,
}));

afterEach(() => {
  cleanup();
});

describe("read page route group (READ-16/21)", () => {
  it("does not leave a read page under the (app) group", () => {
    const frontend = process.cwd();
    expect(
      existsSync(resolve(frontend, "app/(app)/sources/[id]/read/page.tsx")),
    ).toBe(false);
    expect(
      existsSync(resolve(frontend, "app/(read)/sources/[id]/read/page.tsx")),
    ).toBe(true);
  });

  it("renders /read without the app sidebar or auth header", () => {
    render(
      <ReadLayout>
        <ReadPage />
      </ReadLayout>,
    );

    expect(screen.getByTestId("chapter-reader")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Library" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Account" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Log out" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Toggle theme" })).toBeNull();
    expect(screen.queryByText("a@b.c")).toBeNull();
  });

  it("fills the viewport instead of offsetting a 3rem auth header", () => {
    const { container } = render(
      <ReadLayout>
        <ReadPage />
      </ReadLayout>,
    );

    const main = container.querySelector("main");
    expect(main).not.toBeNull();
    expect(main!.className).toContain("h-svh");
    expect(main!.className).not.toContain("100vh-3rem");
    expect(main!.className).not.toContain("3rem");
  });
});
