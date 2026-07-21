// @vitest-environment jsdom

/**
 * E2 gate (closure) — the citation → reader navigation loop is closed (FE-16).
 *
 * A citation's "Open in book" action and the reader speak one anchor contract:
 * the link is built with the anchor encoded exactly once, `useSearchParams`
 * decodes it, and the reader re-encodes it onto the backend request. This proves
 * the whole round-trip end to end for a hostile anchor bearing both a `/` and a
 * `#`: parse the link with `new URL(href, base)` and assert its pathname and
 * decoded `anchor`, then drive the reader with that exact query string and
 * assert the backend section request carried the re-encoded anchor. The reader's
 * table of contents emits the same encode-once section links
 * (tests/toc-panel.test.tsx).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterReader } from "../app/components/chapter-reader";
import { CitationList } from "../app/components/citations";
import { type Citation } from "../app/lib/questions";
import { type ChapterView } from "../app/lib/reading";

// The reader reads the anchor via `useSearchParams` and uses `useRouter` for the
// highlight-capture navigation; drive the params from a mutable holder set per
// test. The citation list does not call either.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
}));

const BASE = "http://localhost";
// The anchor carries both reserved chars — the hostile round-trip case.
const RAW_ANCHOR = "part1/chapter-1.xhtml#core-idea";
const ENCODED_ANCHOR = "part1%2Fchapter-1.xhtml%23core-idea";
const CHAPTER_URL = `/api/sources/s1/chapter?anchor=${ENCODED_ANCHOR}`;

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
  // The citation's Radix Popover reaches for APIs jsdom lacks.
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

// The chapter containing the cited section — the reader now opens whole chapters
// and lands on (scrolls to) the deep-linked section within the flow.
const chapter: ChapterView = {
  chapter_title: "Chapter 1",
  chapter_anchor: RAW_ANCHOR,
  chapter_index: 0,
  chapter_count: 1,
  prev_anchor: null,
  next_anchor: null,
  words_before_chapter: 0,
  chapter_word_count: 7,
  total_word_count: 7,
  sections: [
    {
      anchor: RAW_ANCHOR,
      title: "The First Algorithm",
      section_path: ["Chapter 1", "Core Idea"],
      markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
      word_count: 7,
    },
  ],
  reading_position: null,
};

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
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
    //    onto the backend chapter request and renders the resolved section.
    nav.params = new URLSearchParams(url.search);
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${CHAPTER_URL}`]: () => jsonResponse(200, chapter),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ChapterReader sourceId="s1" />);

    expect(await screen.findByText("Beginnings")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "The First Algorithm" }),
    ).toBeTruthy();
    // The backend chapter request carried the anchor encoded exactly once.
    expect(fetchMock.mock.calls.some(([u]) => u === CHAPTER_URL)).toBe(true);
  });
});
