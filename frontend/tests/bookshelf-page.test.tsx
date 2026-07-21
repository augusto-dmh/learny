// @vitest-environment jsdom

/**
 * C gate (component) — the `/sources` page presents itself as the Bookshelf
 * (HOME-18): the page title reads as a bookshelf and the user's books render as
 * a shelf of tiles. The route stays `/sources` (display-level rename only). The
 * list/upload/ingestion behaviors of the embedded screen are covered by
 * tests/sources-screen.test.tsx; here the focus is the bookshelf framing.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import SourcesPage from "../app/(app)/sources/page";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function routedFetch(handlers: Record<string, () => Response>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler();
  });
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

// A non-ready book keeps the tile free of the quiz/tooltip controls, so the
// shelf renders without radix layout shims.
const book = {
  id: "s1",
  title: "Iron Gall",
  filename: "s1.epub",
  byte_size: 3,
  content_type: "application/epub+zip",
  status: "uploaded",
  created_at: "now",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Bookshelf page (HOME-18)", () => {
  it("titles the page as the bookshelf", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [book]),
      }),
    );

    render(<SourcesPage />);

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("Your bookshelf");
  });

  it("presents the user's books as a shelf of tiles", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [book]),
      }),
    );

    render(<SourcesPage />);

    // The library section lists each owned book as a tile carrying its title.
    const shelf = await screen.findByRole("list");
    expect(within(shelf).getByText("Iron Gall")).toBeTruthy();
  });
});
