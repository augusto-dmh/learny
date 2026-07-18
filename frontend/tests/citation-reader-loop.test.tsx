// @vitest-environment jsdom

/**
 * E2 gate (closure) — the citation → reader navigation loop is closed (FE-16).
 *
 * A citation's "Open in book" action, a sidebar tree node, and the reader all
 * speak one anchor contract: the link is built with the anchor encoded exactly
 * once, `useSearchParams` decodes it, and the reader re-encodes it onto the
 * backend request. This proves the whole round-trip end to end for a hostile
 * anchor bearing both a `/` and a `#`: parse each link with `new URL(href, base)`
 * and assert its pathname and decoded `anchor`, then drive the reader with that
 * exact query string and assert the backend section request carried the
 * re-encoded anchor.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { CitationList } from "../app/components/citations";
import { SectionReader } from "../app/components/section-reader";
import { AppSidebar } from "../app/components/shell/app-sidebar";
import { type Citation } from "../app/lib/questions";
import { SidebarProvider } from "../components/ui/sidebar";

// The reader reads the anchor via `useSearchParams` and uses `useRouter` for the
// highlight-capture navigation; drive the params from a mutable holder set per
// test. The sidebar and citation list do not call either.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
}));

const BASE = "http://localhost";
// The anchor carries both reserved chars — the hostile round-trip case.
const RAW_ANCHOR = "part1/chapter-1.xhtml#core-idea";
const ENCODED_ANCHOR = "part1%2Fchapter-1.xhtml%23core-idea";
const SECTION_URL = `/api/sources/s1/section?anchor=${ENCODED_ANCHOR}`;

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
  // Radix Popover + shadcn Sidebar reach for APIs jsdom lacks.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
});

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

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

const citation: Citation = {
  chunk_id: "c1",
  source_id: "s1",
  section_path: ["Chapter 1", "Core Idea"],
  anchor: RAW_ANCHOR,
  page_span: null,
  snippet: "the first algorithm ever written",
  score: 0.03,
};

const section = {
  anchor: RAW_ANCHOR,
  title: "The First Algorithm",
  section_path: ["Chapter 1", "Core Idea"],
  markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
};

const readySource = {
  id: "s1",
  title: "Ready Book",
  filename: "s1.epub",
  byte_size: 3,
  content_type: "application/epub+zip",
  status: "ready",
  created_at: "now",
};

// A structure whose deepest section anchor also carries a `/` and a `#`.
const readyStructure = {
  title: "Ready Book",
  authors: ["Ada Lovelace"],
  language: "en",
  sections: [
    {
      title: "Chapter 1",
      depth: 0,
      section_path: ["Chapter 1"],
      anchor: "chapter-1.xhtml",
      children: [
        {
          title: "Core Idea",
          depth: 1,
          section_path: ["Chapter 1", "Core Idea"],
          anchor: RAW_ANCHOR,
          children: [],
        },
      ],
    },
  ],
};

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  // shadcn SidebarProvider reads the viewport via matchMedia, absent in jsdom.
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
  vi.restoreAllMocks();
});

describe("citation → reader loop (E2)", () => {
  it("opening a citation lands the reader on that exact section", async () => {
    // 1. Render the citation and read its "Open in book" href.
    const first = render(<CitationList sourceId="s1" citations={[citation]} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Citation: Chapter 1 › Core Idea" }),
    );
    const href = screen
      .getByRole("link", { name: /open in book/i })
      .getAttribute("href")!;

    // The link targets the reader route, and its anchor decodes to the raw anchor.
    const url = new URL(href, BASE);
    expect(url.pathname).toBe("/sources/s1/read");
    expect(url.searchParams.get("anchor")).toBe(RAW_ANCHOR);
    first.unmount();

    // 2. Drive the reader with that exact query string; it re-encodes the anchor
    //    onto the backend request and renders the resolved section.
    nav.params = new URLSearchParams(url.search);
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SectionReader sourceId="s1" />);

    expect(await screen.findByText("Beginnings")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "The First Algorithm" }),
    ).toBeTruthy();
    // The backend section request carried the anchor encoded exactly once.
    expect(fetchMock.mock.calls.some(([u]) => u === SECTION_URL)).toBe(true);
  });

  it("a sidebar tree node targets the reader at the section's anchor", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        "GET /api/sources/s1/structure": () =>
          jsonResponse(200, readyStructure),
      }),
    );

    render(
      <SidebarProvider>
        <AppSidebar />
      </SidebarProvider>,
    );

    fireEvent.click(await screen.findByText("Ready Book"));

    const link = await screen.findByRole("link", { name: "Core Idea" });
    const url = new URL(link.getAttribute("href")!, BASE);
    expect(url.pathname).toBe("/sources/s1/read");
    expect(url.searchParams.get("anchor")).toBe(RAW_ANCHOR);
  });
});
