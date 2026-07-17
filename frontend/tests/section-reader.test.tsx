// @vitest-environment jsdom

/**
 * E1 gate (component) — the section reader opens a cited passage in context. It
 * reads the anchor from the URL (decoded by `useSearchParams`), re-encodes it
 * exactly once onto the backend section request, renders the section's markdown
 * with its heading brought into view and transiently highlighted (FE-15), shows
 * a pick-a-section empty state with no anchor and a readable not-found state for
 * an unknown anchor (FE-17), and never injects raw HTML in the markdown as live
 * DOM (reader XSS edge case).
 */

import {
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SectionReader } from "../app/components/section-reader";

// The component reads the anchor via `useSearchParams`; drive it from a mutable
// holder set per test (constructed from a percent-encoded query string, so
// `.get()` decodes exactly as the browser does).
const nav = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
}));

// scrollIntoView is not implemented in jsdom; a spy both polyfills it and records
// the call the reader makes when a section resolves.
beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`; fail loudly on anything unexpected. */
function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

// An anchor carrying both a `/` and a `#` — the hostile round-trip case.
const RAW_ANCHOR = "part1/chapter-1.xhtml#core-idea";
const ENCODED_ANCHOR = "part1%2Fchapter-1.xhtml%23core-idea";
const SECTION_URL = `/api/sources/s1/section?anchor=${ENCODED_ANCHOR}`;

const section = {
  anchor: RAW_ANCHOR,
  title: "The First Algorithm",
  section_path: ["Chapter 1", "Core Idea"],
  markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
};

beforeEach(() => {
  nav.params = new URLSearchParams(`anchor=${ENCODED_ANCHOR}`);
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SectionReader (E1)", () => {
  it("re-encodes the decoded anchor onto the request and renders the section markdown", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SectionReader sourceId="s1" />);

    // Heading and paragraph from the rendered markdown are visible.
    expect(await screen.findByText("Beginnings")).toBeTruthy();
    await waitFor(() =>
      expect(document.body.textContent).toContain(
        "Ada Lovelace wrote the first algorithm.",
      ),
    );

    // The section title and breadcrumb render.
    expect(screen.getByRole("heading", { name: "The First Algorithm" })).toBeTruthy();
    expect(screen.getByText("Chapter 1 › Core Idea")).toBeTruthy();

    // The backend saw the anchor encoded exactly once (round-trip proof).
    expect(
      fetchMock.mock.calls.some(([url]) => url === SECTION_URL),
    ).toBe(true);
  });

  it("scrolls the heading into view and applies a transient highlight", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
      }),
    );

    render(<SectionReader sourceId="s1" />);

    const title = await screen.findByTestId("section-title");
    // The heading block is highlighted on load...
    expect(title.getAttribute("data-highlight")).toBe("on");
    // ...and it was scrolled into view.
    await waitFor(() =>
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled(),
    );
  });

  it("renders a readable not-found state with a way back for an unknown anchor", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${SECTION_URL}`]: () => new Response(null, { status: 404 }),
      }),
    );

    render(<SectionReader sourceId="s1" />);

    expect(await screen.findByText(/couldn.t find that section/i)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /back to your library/i }).getAttribute("href"),
    ).toBe("/sources");
  });

  it("shows a pick-a-section empty state when no anchor is present", async () => {
    nav.params = new URLSearchParams();
    // No fetch should be issued without an anchor.
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    render(<SectionReader sourceId="s1" />);

    expect(
      await screen.findByText(/pick a section from the sidebar/i),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not inject raw HTML in the markdown as live DOM", async () => {
    const hostileSection = {
      ...section,
      markdown:
        "Intro paragraph.\n\n<script>window.__xss = 1;</script>\n\n<img src=x onerror=\"window.__xss = 1\">",
    };
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${SECTION_URL}`]: () => jsonResponse(200, hostileSection),
      }),
    );

    const { container } = render(<SectionReader sourceId="s1" />);
    await screen.findByText(/intro paragraph/i);

    // No live <script> node, and no <img> carrying an onerror handler, was
    // injected — the renderer escapes raw HTML rather than parsing it.
    expect(container.querySelector("script")).toBeNull();
    for (const img of Array.from(container.querySelectorAll("img"))) {
      expect(img.getAttribute("onerror")).toBeNull();
    }
    expect(
      (globalThis as { __xss?: number }).__xss,
    ).toBeUndefined();
  });
});
