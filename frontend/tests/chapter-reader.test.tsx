// @vitest-environment jsdom

/**
 * B2 (RD-03/04) — the chapter flow renders one chapter as a single continuous
 * article. Every section lays out in order inside one `.prose-reading` article,
 * each wrapped in a `<section id={anchor} data-section-anchor>` DOM node; the
 * deep-link / resume target is scrolled into view and its section heading
 * transiently highlighted; and highlight capture (NF-12) resolves each selection
 * against the right section's served Markdown (never the DOM), POSTing that
 * section's anchor. Raw HTML in the markdown stays inert (reader XSS edge) and
 * corpus punctuation renders verbatim (IDF-06).
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import type { ChapterView } from "../app/lib/reading";

// The component reads `useRouter().push` for the "Highlight + note" navigation;
// spy it. `useSearchParams` is stubbed for the orchestrator tests that share this
// mock (B3/B4).
const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useParams: () => ({ id: "s1" }),
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

// Two-section chapter with fragment-bearing anchors (`path#fragment`); the
// structural section titles differ from the markdown headings so heading queries
// stay unambiguous.
const S1 = "part1/ch1.xhtml#s1";
const S2 = "part1/ch1.xhtml#s2";
const HIGHLIGHTS_URL = "/api/sources/s1/highlights";

const chapter: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: S1,
  chapter_index: 0,
  chapter_count: 2,
  prev_anchor: null,
  next_anchor: "part1/ch2.xhtml#s1",
  words_before_chapter: 0,
  chapter_word_count: 14,
  total_word_count: 40,
  sections: [
    {
      anchor: S1,
      title: "The First Algorithm",
      section_path: ["Chapter One", "Beginnings"],
      markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
      word_count: 8,
    },
    {
      anchor: S2,
      title: "The Analytical Engine",
      section_path: ["Chapter One", "Mechanism"],
      markdown: "## Mechanism\n\nBabbage designed the analytical engine.",
      word_count: 6,
    },
  ],
  reading_position: null,
};

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

beforeEach(() => {
  nav.push.mockClear();
  nav.replace.mockClear();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ChapterFlow render (RD-03)", () => {
  it("renders every section in order, each wrapped in its anchor DOM id", async () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    // Both section bodies render, in order, inside one .prose-reading article.
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(
      screen.getByText("Babbage designed the analytical engine."),
    ).toBeTruthy();

    const wrappers = Array.from(
      container.querySelectorAll("[data-section-anchor]"),
    );
    // Sections in chapter order, each carrying its anchor as both the wrapper id
    // (the deep-link target) and the data attribute (the scroll observer's hook).
    expect(wrappers.map((w) => w.getAttribute("data-section-anchor"))).toEqual([
      S1,
      S2,
    ]);
    expect(wrappers.map((w) => w.id)).toEqual([S1, S2]);

    // Structural section titles render as headings.
    expect(
      screen.getByRole("heading", { name: "The First Algorithm" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "The Analytical Engine" }),
    ).toBeTruthy();
  });

  it("renders the book prose under the reading-typography class", async () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    const prose = container.querySelector(".prose-reading");
    expect(prose).not.toBeNull();
    expect(prose!.textContent).toContain(
      "Ada Lovelace wrote the first algorithm.",
    );
  });

  it("renders corpus punctuation verbatim, never rewriting book text", async () => {
    // IDF-06: typographic discipline is UI-copy-only — quotes, dashes, and
    // ellipses already in the corpus text pass through untouched.
    const punctuation =
      "She said \"so-called 'algorithms'\" -- then paused... twice.";
    const withPunctuation: ChapterView = {
      ...chapter,
      sections: [{ ...chapter.sections[0], markdown: punctuation }, chapter.sections[1]],
    };

    render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={withPunctuation}
        scrollTarget={null}
      />,
    );

    await waitFor(() =>
      expect(document.body.textContent).toContain(punctuation),
    );
  });

  it("does not inject raw HTML in the markdown as live DOM", async () => {
    const hostile: ChapterView = {
      ...chapter,
      sections: [
        {
          ...chapter.sections[0],
          markdown:
            "Intro paragraph.\n\n<script>window.__xss = 1;</script>\n\n<img src=x onerror=\"window.__xss = 1\">",
        },
        chapter.sections[1],
      ],
    };

    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={hostile} scrollTarget={null} />,
    );
    await screen.findByText(/intro paragraph/i);

    expect(container.querySelector("script")).toBeNull();
    for (const img of Array.from(container.querySelectorAll("img"))) {
      expect(img.getAttribute("onerror")).toBeNull();
    }
    expect((globalThis as { __xss?: number }).__xss).toBeUndefined();
  });
});

describe("ChapterFlow deep-link scroll (RD-04)", () => {
  it("scrolls the fragment-bearing target section into view and flashes only its heading", async () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={S2} />,
    );

    // The `#fragment`-bearing anchor resolved via getElementById (a CSS selector
    // could not match the `#`) and was scrolled into view.
    await waitFor(() =>
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled(),
    );

    // Only the targeted section's heading carries the transient highlight.
    const flashed = container.querySelector(`[data-section-heading="${S2}"]`);
    const other = container.querySelector(`[data-section-heading="${S1}"]`);
    expect(flashed?.getAttribute("data-highlight")).toBe("on");
    expect(other?.getAttribute("data-highlight")).toBe("off");
  });

  it("does not scroll or flash any section when there is no target", async () => {
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    for (const heading of Array.from(
      container.querySelectorAll("[data-section-heading]"),
    )) {
      expect(heading.getAttribute("data-highlight")).toBe("off");
    }
  });
});

describe("ChapterFlow capture (NF-12)", () => {
  /** Render the flow, select `text`, and mouse-up over the given section. */
  function renderAndSelect(anchor: string, text: string) {
    const view = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    selectText(text);
    fireEvent.mouseUp(
      view.container.querySelector(`[data-section-anchor="${anchor}"]`)!,
    );
    return view;
  }

  it("raises the capture popover on a selection resolvable in the section", () => {
    renderAndSelect(S1, "Ada Lovelace wrote the first algorithm");

    expect(
      screen.getByRole("dialog", { name: "Capture highlight" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Highlight" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Highlight + note" }),
    ).toBeTruthy();
  });

  it("does not raise the popover for a selection absent from the section markdown", () => {
    renderAndSelect(S1, "a phrase that is not in the section");

    expect(
      screen.queryByRole("dialog", { name: "Capture highlight" }),
    ).toBeNull();
  });

  it("captures against the moused-up section's markdown, POSTing that section's anchor", async () => {
    const capturedNote = {
      id: "n1",
      title: "Babbage designed the analytical engine",
      body_markdown: "",
      tags: [],
      anchors: [],
      created_at: "now",
      updated_at: "now",
    };
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
    });
    vi.stubGlobal("fetch", fetchMock);

    // Select text that lives in section TWO and mouse-up over section two.
    renderAndSelect(S2, "Babbage designed the analytical engine");
    await screen.findByRole("dialog", { name: "Capture highlight" });
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === HIGHLIGHTS_URL),
      ).toBe(true),
    );
    const post = fetchMock.mock.calls.find(([url]) => url === HIGHLIGHTS_URL)!;
    const init = post[1] as RequestInit;
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    // The payload carries section TWO's anchor and its context sliced from
    // section two's Markdown — proof the selection resolved against the right
    // section, not the first one.
    expect(JSON.parse(init.body as string)).toEqual({
      anchor: S2,
      quote_exact: "Babbage designed the analytical engine",
      quote_prefix: "## Mechanism ",
      quote_suffix: ".",
      title: "Babbage designed the analytical engine",
    });
    // The popover closes once the capture succeeds; a bare highlight does not navigate.
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Capture highlight" }),
      ).toBeNull(),
    );
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("opens the created note after Highlight + note", async () => {
    const capturedNote = {
      id: "n7",
      title: "Ada",
      body_markdown: "",
      tags: [],
      anchors: [],
      created_at: "now",
      updated_at: "now",
    };
    vi.stubGlobal(
      "fetch",
      routedFetch({ [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote) }),
    );

    renderAndSelect(S1, "Ada Lovelace wrote the first algorithm");
    await screen.findByRole("dialog", { name: "Capture highlight" });
    fireEvent.click(screen.getByRole("button", { name: "Highlight + note" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes/n7"));
  });

  it("shows a reload prompt when the capture is stale (409)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${HIGHLIGHTS_URL}`]: () =>
          jsonResponse(409, { detail: "The book changed while you were reading." }),
      }),
    );

    renderAndSelect(S1, "Ada Lovelace wrote the first algorithm");
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
