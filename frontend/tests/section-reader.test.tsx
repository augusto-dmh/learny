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
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SectionReader } from "../app/components/section-reader";

// The component reads the anchor via `useSearchParams`; drive it from a mutable
// holder set per test (constructed from a percent-encoded query string, so
// `.get()` decodes exactly as the browser does). `useRouter().push` is spied so
// the "Highlight + note" navigation to the created note can be asserted.
const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
}));

/** Stub `window.getSelection` to return `text` as the current selection. */
function selectText(text: string) {
  window.getSelection = () =>
    ({
      toString: () => text,
      rangeCount: 0,
      getRangeAt: () => ({ getBoundingClientRect: () => undefined }),
    }) as unknown as Selection;
}

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
  nav.push.mockClear();
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

  it("renders corpus punctuation verbatim, never rewriting book text", async () => {
    // IDF-06: typographic discipline applies to UI copy only — quotes, dashes,
    // and ellipses already in the corpus text pass through untouched.
    const punctuation =
      "She said \"so-called 'algorithms'\" -- then paused... twice.";
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${SECTION_URL}`]: () =>
        jsonResponse(200, { ...section, markdown: punctuation }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SectionReader sourceId="s1" />);

    // Rendered text equals served text: straight quotes stay straight, double
    // hyphens stay double, three dots stay three dots.
    await waitFor(() =>
      expect(document.body.textContent).toContain(punctuation),
    );
  });

  it("renders the book prose under the reading-typography class", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<SectionReader sourceId="s1" />);

    await screen.findByText("Beginnings");
    // The markdown wrapper carries .prose-reading (class presence, not pixels —
    // jsdom applies no stylesheets), and the prose lives inside it.
    const prose = container.querySelector(".prose-reading");
    expect(prose).not.toBeNull();
    expect(prose!.textContent).toContain(
      "Ada Lovelace wrote the first algorithm.",
    );
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

  it("does not raise the capture popover for a selection absent from the markdown", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
      }),
    );

    const { container } = render(<SectionReader sourceId="s1" />);
    await screen.findByText("Beginnings");

    // A formatting-only span the reader shows but the Markdown does not hold
    // verbatim resolves to nothing → no popover.
    selectText("a phrase that is not in the section");
    fireEvent.mouseUp(container.querySelector(".prose-reading")!);

    expect(screen.queryByRole("dialog", { name: "Capture highlight" })).toBeNull();
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

// The selection the reader captures, verbatim in the section Markdown
// ("## Beginnings\n\nAda Lovelace wrote the first algorithm.").
const SELECTED = "Ada Lovelace wrote the first algorithm";
const HIGHLIGHTS_URL = "/api/sources/s1/highlights";

const capturedNote = {
  id: "n1",
  title: SELECTED,
  body_markdown: "",
  tags: [],
  anchors: [
    {
      id: "a1",
      source_id: "s1",
      source_title: "Ready Book",
      anchor: RAW_ANCHOR,
      section_path: ["Chapter 1", "Core Idea"],
      block_ordinal: 0,
      start_offset: 0,
      end_offset: 38,
      quote_exact: SELECTED,
      quote_prefix: "## Beginnings ",
      quote_suffix: ".",
      status: "active",
    },
  ],
  created_at: "now",
  updated_at: "now",
};

/** Render the reader, wait for the section, then select `SELECTED` and mouse-up. */
async function renderAndSelect(handlers: Record<string, Handler>) {
  const fetchMock = routedFetch({
    "GET /api/auth/me": () => authedMe.clone(),
    [`GET ${SECTION_URL}`]: () => jsonResponse(200, section),
    ...handlers,
  });
  vi.stubGlobal("fetch", fetchMock);

  const view = render(<SectionReader sourceId="s1" />);
  await screen.findByText("Beginnings");
  selectText(SELECTED);
  fireEvent.mouseUp(view.container.querySelector(".prose-reading")!);
  return fetchMock;
}

describe("SectionReader capture (NF-12)", () => {
  it("raises the capture popover with both actions on a resolvable selection", async () => {
    await renderAndSelect({});

    const popover = await screen.findByRole("dialog", {
      name: "Capture highlight",
    });
    expect(popover).toBeTruthy();
    expect(screen.getByRole("button", { name: "Highlight" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Highlight + note" })).toBeTruthy();
  });

  it("captures a bare highlight with the selection payload resolved against the markdown", async () => {
    const fetchMock = await renderAndSelect({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
    });

    await screen.findByRole("dialog", { name: "Capture highlight" });
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            url === HIGHLIGHTS_URL && (init as RequestInit)?.method === "POST",
        ),
      ).toBe(true),
    );
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === HIGHLIGHTS_URL && (init as RequestInit)?.method === "POST",
    )!;
    const init = post[1] as RequestInit;
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    // The quote is whitespace-normalized and its 32-char context is sliced from
    // the served Markdown (never the DOM); prefix carries the heading, suffix the
    // trailing period.
    expect(JSON.parse(init.body as string)).toEqual({
      anchor: RAW_ANCHOR,
      quote_exact: SELECTED,
      quote_prefix: "## Beginnings ",
      quote_suffix: ".",
      title: SELECTED,
    });
    // A bare highlight does not navigate away.
    expect(nav.push).not.toHaveBeenCalled();
    // The popover closes once the capture succeeds.
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Capture highlight" }),
      ).toBeNull(),
    );
  });

  it("opens the created note after Highlight + note", async () => {
    await renderAndSelect({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
    });

    await screen.findByRole("dialog", { name: "Capture highlight" });
    fireEvent.click(screen.getByRole("button", { name: "Highlight + note" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes/n1"));
  });

  it("shows a reload prompt when the capture is stale (409)", async () => {
    await renderAndSelect({
      [`POST ${HIGHLIGHTS_URL}`]: () =>
        jsonResponse(409, { detail: "The book changed while you were reading." }),
    });

    await screen.findByRole("dialog", { name: "Capture highlight" });
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/reload the page/i);
    // The popover stays open so the user can retry after reloading.
    expect(
      screen.getByRole("dialog", { name: "Capture highlight" }),
    ).toBeTruthy();
  });
});
