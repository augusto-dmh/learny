// @vitest-environment jsdom

/**
 * C gate (component) — the library sidebar lists the user's sources with status
 * badges, links source entries to Ask/Teach/Read, lazily expands a ready
 * source's section tree from the structure endpoint, builds each tree link with
 * the anchor encoded exactly once, and shows an empty-library state with an
 * upload affordance (FE-03/FE-04 + empty-library edge case).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "../app/components/shell/app-sidebar";
import { SidebarProvider } from "../components/ui/sidebar";

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

function sourceRow(id: string, title: string, status: string) {
  return {
    id,
    title,
    filename: `${id}.epub`,
    byte_size: 3,
    content_type: "application/epub+zip",
    status,
    created_at: "now",
  };
}

/** One source in each of the four projection states. */
const mixed = [
  sourceRow("s-up", "Uploaded Book", "uploaded"),
  sourceRow("s-proc", "Processing Book", "processing"),
  sourceRow("s-ready", "Ready Book", "ready"),
  sourceRow("s-fail", "Failed Book", "failed"),
];

/**
 * Structure whose deepest section anchor carries both a `/` and a `#`, so the
 * link-build encoding (encodeURIComponent exactly once) is observable.
 */
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
          anchor: "text/chapter-1.xhtml#core-idea",
          children: [],
        },
      ],
    },
  ],
};

function renderSidebar() {
  return render(
    <SidebarProvider>
      <AppSidebar />
    </SidebarProvider>,
  );
}

beforeEach(() => {
  // next-themes/shadcn SidebarProvider reads the viewport via matchMedia, absent
  // in jsdom; stub it to a stable (desktop) match.
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

describe("AppSidebar", () => {
  it("lists each source with its status badge", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/sources": () => jsonResponse(200, mixed) }),
    );

    renderSidebar();

    await screen.findByText("Ready Book");
    // Every source title renders...
    for (const title of [
      "Uploaded Book",
      "Processing Book",
      "Ready Book",
      "Failed Book",
    ]) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    // ...alongside its exact status text as a badge.
    for (const status of ["uploaded", "processing", "ready", "failed"]) {
      expect(screen.getByText(status)).toBeTruthy();
    }
  });

  it("links a ready source entry to its Ask and Teach panel modes and Read view", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/sources": () => jsonResponse(200, [mixed[2]]) }),
    );

    renderSidebar();

    fireEvent.click(await screen.findByText("Ready Book"));

    // Ask and Teach now deep-link into the reader with the matching panel open.
    const ask = await screen.findByRole("link", { name: "Ask" });
    expect(ask.getAttribute("href")).toBe("/sources/s-ready/read?panel=ask");
    expect(
      screen.getByRole("link", { name: "Teach" }).getAttribute("href"),
    ).toBe("/sources/s-ready/read?panel=teach");
    expect(
      screen.getByRole("link", { name: "Read" }).getAttribute("href"),
    ).toBe("/sources/s-ready/read");
  });

  it("expands a ready source's section tree from the structure endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(200, readyStructure),
      }),
    );

    renderSidebar();

    // The tree is not fetched until the source is expanded.
    fireEvent.click(await screen.findByText("Ready Book"));

    // Both nested section titles render once the structure loads.
    expect(await screen.findByText("Core Idea")).toBeTruthy();
    expect(screen.getByText("Chapter 1")).toBeTruthy();
  });

  it("caches the section tree across collapse and re-expand", async () => {
    let structureCalls = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () => {
          structureCalls += 1;
          return jsonResponse(200, readyStructure);
        },
      }),
    );

    renderSidebar();

    const trigger = await screen.findByText("Ready Book");

    // First expand fetches the structure once and renders the tree.
    fireEvent.click(trigger);
    expect(await screen.findByText("Core Idea")).toBeTruthy();
    expect(structureCalls).toBe(1);

    // Collapse tears the tree down.
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.queryByText("Core Idea")).toBeNull());

    // Re-expand renders the cached tree without a second fetch.
    fireEvent.click(trigger);
    expect(await screen.findByText("Core Idea")).toBeTruthy();
    expect(structureCalls).toBe(1);
  });

  it("builds each tree link with the anchor encoded exactly once", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(200, readyStructure),
      }),
    );

    renderSidebar();

    fireEvent.click(await screen.findByText("Ready Book"));

    // The `/`- and `#`-bearing anchor is percent-encoded once for the query.
    const deep = await screen.findByRole("link", { name: "Core Idea" });
    expect(deep.getAttribute("href")).toBe(
      "/sources/s-ready/read?anchor=text%2Fchapter-1.xhtml%23core-idea",
    );
    // A plain anchor still round-trips.
    expect(
      screen.getByRole("link", { name: "Chapter 1" }).getAttribute("href"),
    ).toBe("/sources/s-ready/read?anchor=chapter-1.xhtml");
  });

  it("offers a global Review entry linking to the due queue", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/sources": () => jsonResponse(200, []) }),
    );

    renderSidebar();

    const review = await screen.findByRole("link", { name: "Review" });
    expect(review.getAttribute("href")).toBe("/review");
  });

  it("shows an empty-library state with an upload affordance", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/sources": () => jsonResponse(200, []) }),
    );

    renderSidebar();

    expect(await screen.findByText("Your library is empty.")).toBeTruthy();
    const upload = screen.getByRole("link", { name: "Upload a book" });
    expect(upload.getAttribute("href")).toBe("/sources");
  });
});
