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
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterFlow, ChapterReader } from "../app/components/chapter-reader";
import type { ObserverFactory } from "../app/components/use-scroll-position";
import type { ChapterView, SourceHighlightView } from "../app/lib/reading";

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

// Anchors the mocked teach panel jumps to via `onShowInBook`: one inside the
// loaded chapter (an in-flow scroll) and one in another chapter (a navigation).
const jump = vi.hoisted(() => ({
  inChapter: "part1/ch1.xhtml#s2",
  foreign: "part1/ch2.xhtml#s1",
}));

// These reader tests exercise panel *wiring* (open/close/mode/URL and the
// show-in-book jump), not the chat internals — the Ask/Teach panels are
// unit-tested in their own files and pull in AI-Elements (ResizeObserver,
// streaming). Stub them to body markers so mounting the reader with a panel open
// stays lightweight; the teach stub also surfaces the `onShowInBook` wiring so the
// citation-jump handler can be driven from a real click (RA-13/14).
vi.mock("../app/components/ask-panel", () => ({
  AskPanel: ({
    pendingRequest,
  }: {
    pendingRequest?: { kind: string; quote: string; anchor: string } | null;
  }) => (
    <div data-testid="ask-panel-body">
      {pendingRequest ? (
        <span data-testid="pending-request">
          {pendingRequest.kind}|{pendingRequest.quote}|{pendingRequest.anchor}
        </span>
      ) : null}
    </div>
  ),
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: ({
    onShowInBook,
  }: {
    onShowInBook?: (anchor: string) => void;
  }) => (
    <div data-testid="teach-panel-body">
      <button type="button" onClick={() => onShowInBook?.(jump.inChapter)}>
        show-in-chapter
      </button>
      <button type="button" onClick={() => onShowInBook?.(jump.foreign)}>
        show-foreign
      </button>
    </div>
  ),
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
  words_before_chapter: 100,
  chapter_word_count: 500,
  total_word_count: 1000,
  sections: [
    {
      anchor: S1,
      title: "The First Algorithm",
      section_path: ["Chapter One", "Beginnings"],
      markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
      word_count: 300,
    },
    {
      anchor: S2,
      title: "The Analytical Engine",
      section_path: ["Chapter One", "Mechanism"],
      markdown: "## Mechanism\n\nBabbage designed the analytical engine.",
      word_count: 200,
    },
  ],
  reading_position: null,
};

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

// The orchestrator reads the anchor from `useSearchParams`; the S2 deep-link and
// the URL the client re-encodes it onto.
const ENCODED_S2 = "part1%2Fch1.xhtml%23s2";
const CHAPTER_URL_S2 = `/api/sources/s1/chapter?anchor=${ENCODED_S2}`;
const CHAPTER_URL_RESUME = "/api/sources/s1/chapter";

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

/** A promise whose resolution the test controls, to observe in-flight fetches. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/**
 * An injectable IntersectionObserver stand-in: records observed elements and lets
 * the test drive the callback with per-anchor intersection states.
 */
function fakeObserver() {
  const observed: Element[] = [];
  let cb: IntersectionObserverCallback | null = null;
  const factory: ObserverFactory = (callback) => {
    cb = callback;
    return {
      observe: (el: Element) => observed.push(el),
      unobserve: () => {},
      disconnect: () => {},
      takeRecords: () => [],
      root: null,
      rootMargin: "",
      thresholds: [],
    } as unknown as IntersectionObserver;
  };
  function emit(states: Record<string, boolean>) {
    const entries = observed
      .map((el) => {
        const anchor = el.getAttribute("data-section-anchor")!;
        return anchor in states
          ? ({
              target: el,
              isIntersecting: states[anchor],
            } as unknown as IntersectionObserverEntry)
          : null;
      })
      .filter((e): e is IntersectionObserverEntry => e !== null);
    act(() => cb?.(entries, {} as IntersectionObserver));
  }
  return { factory, emit };
}

beforeEach(() => {
  nav.params = new URLSearchParams();
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

  it("keeps the chapter title visible in a sticky boundary element (RD-05)", async () => {
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    const topBar = screen.getByTestId("reader-top-bar");
    // The boundary carries the current chapter title...
    expect(topBar.textContent).toContain("Chapter One");
    // ...and its positioning container is sticky at the viewport top, so the
    // title stays visible while the chapter scrolls underneath it.
    const stickyContainer = topBar.parentElement!;
    expect(stickyContainer.className).toContain("sticky");
    expect(stickyContainer.className).toContain("top-0");
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

  it("raises the five-verb capture popover on a selection resolvable in the section", () => {
    renderAndSelect(S1, "Ada Lovelace wrote the first algorithm");

    // The reader wires the panel-bound verbs, so the popover carries all five
    // (Highlight/Note keep the existing capture flow; RA-15/16).
    expect(
      screen.getByRole("dialog", { name: "Capture highlight" }),
    ).toBeTruthy();
    for (const verb of ["Highlight", "Note", "Explain", "Ask", "Create card"]) {
      expect(screen.getByRole("button", { name: verb })).toBeTruthy();
    }
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

  it("opens the created note after the Note verb", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "Note" }));

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

describe("ChapterReader orchestration (RD-26/27/10)", () => {
  it("dispatches the auth and chapter fetches in parallel and shows a skeleton while pending", async () => {
    const authD = deferred<Response>();
    const chapterD = deferred<Response>();
    const fetchMock = vi.fn((url: string) => {
      if (url === "/api/auth/me") return authD.promise;
      if (url.startsWith("/api/sources/s1/chapter")) return chapterD.promise;
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);

    render(<ChapterReader sourceId="s1" />);

    // Both requests are dispatched before EITHER resolves — a sequential
    // auth→content chain would issue only the auth call at this point.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls).toContain("/api/auth/me");
    expect(urls).toContain(CHAPTER_URL_S2);

    // While both are pending the reader shows a reading-surface skeleton, not
    // bare "Loading…" text.
    expect(screen.getByTestId("reading-skeleton")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();

    // Resolving both renders the chapter.
    authD.resolve(authedMe.clone());
    chapterD.resolve(jsonResponse(200, chapter));
    expect(
      await screen.findByText("Ada Lovelace wrote the first algorithm."),
    ).toBeTruthy();
  });

  it("redirects to login when the content fetch is unauthenticated (401)", async () => {
    const onRequireAuth = vi.fn();
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
        [`GET ${CHAPTER_URL_S2}`]: () => new Response(null, { status: 401 }),
      }),
    );

    render(<ChapterReader sourceId="s1" onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalled());
    expect(await screen.findByText(/signed out/i)).toBeTruthy();
  });

  it("shows a readable not-found state with a way back for an unknown anchor", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${CHAPTER_URL_S2}`]: () => new Response(null, { status: 404 }),
      }),
    );

    render(<ChapterReader sourceId="s1" />);

    expect(await screen.findByText(/couldn.t find that chapter/i)).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: /back to your library/i })
        .getAttribute("href"),
    ).toBe("/sources");
  });

  it("resumes the stored position's chapter scrolled to the stored anchor with no ?anchor=", async () => {
    // No URL anchor → the client omits the query and the server resumes; the
    // routed key without a query string proves the anchor was omitted.
    nav.params = new URLSearchParams();
    const resumed: ChapterView = {
      ...chapter,
      reading_position: { anchor: S2, percent: 40, updated_at: "now" },
    };
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${CHAPTER_URL_RESUME}`]: () => jsonResponse(200, resumed),
      }),
    );

    render(<ChapterReader sourceId="s1" />);

    await screen.findByText("Babbage designed the analytical engine.");
    // Scrolled to the stored section, whose heading carries the transient flash.
    await waitFor(() =>
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled(),
    );
    const flashed = document.querySelector(`[data-section-heading="${S2}"]`);
    expect(flashed?.getAttribute("data-highlight")).toBe("on");
  });
});

describe("ChapterFlow highlight painting (RD-28/29)", () => {
  // Both sections contain the identical phrase; the highlight is anchored to
  // section one only, proving painting is scoped to the anchoring section.
  const SHARED = "the analytical engine";
  const shared: ChapterView = {
    ...chapter,
    sections: [
      {
        ...chapter.sections[0],
        markdown: "## Beginnings\n\nBabbage built the analytical engine.",
      },
      {
        ...chapter.sections[1],
        markdown: "## Mechanism\n\nAda praised the analytical engine.",
      },
    ],
  };

  function highlight(over: Partial<SourceHighlightView>): SourceHighlightView {
    return {
      note_id: "n1",
      note_title: SHARED,
      has_body: false,
      anchor: S1,
      quote_exact: SHARED,
      quote_prefix: "",
      quote_suffix: "",
      status: "active",
      ...over,
    };
  }

  it("paints an active highlight in its anchoring section only", async () => {
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={shared}
        scrollTarget={null}
        highlights={[highlight({ note_id: "n5" })]}
      />,
    );
    await screen.findByText(/Babbage built/);

    // Exactly one mark, in section one — even though section two holds the same
    // phrase, no highlight is anchored there, so it stays unpainted.
    await waitFor(() =>
      expect(container.querySelectorAll("mark.reader-highlight")).toHaveLength(1),
    );
    const mark = container.querySelector("mark.reader-highlight")!;
    expect(mark.getAttribute("data-note-id")).toBe("n5");
    expect(mark.textContent).toBe(SHARED);
    const s1El = container.querySelector(`[data-section-anchor="${S1}"]`)!;
    const s2El = container.querySelector(`[data-section-anchor="${S2}"]`)!;
    expect(s1El.contains(mark)).toBe(true);
    expect(s2El.contains(mark)).toBe(false);
  });

  it("does not paint a stale highlight even when its quote is present", async () => {
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={shared}
        scrollTarget={null}
        highlights={[highlight({ status: "stale" })]}
      />,
    );
    await screen.findByText(/Babbage built/);

    // Give any paint effect a chance to run, then confirm nothing was painted.
    await waitFor(() =>
      expect(screen.getByText(/Ada praised/)).toBeTruthy(),
    );
    expect(container.querySelectorAll("mark.reader-highlight")).toHaveLength(0);
  });
});

describe("ChapterFlow fixture-scale render (RFC assumption)", () => {
  it("lays out a large multi-section chapter in one pass with every section present", async () => {
    // A synthetic chapter at book scale (~10k words across many sections): the
    // RFC assumes a full chapter renders without windowing. Each section ends in
    // a unique sentinel so the first and last both being present proves the whole
    // chapter laid out, not a truncated head.
    const SECTIONS = 16;
    const sentence =
      "Ada Lovelace annotated the analytical engine and foresaw that machines might one day compose music and manipulate symbols beyond calculation. ";
    const sections = Array.from({ length: SECTIONS }, (_, i) => ({
      anchor: `part1/ch1.xhtml#s${i}`,
      title: `Section ${i}`,
      section_path: ["Chapter One", `Section ${i}`],
      markdown: `## Section ${i}\n\n${sentence.repeat(40)}\n\nMarker ${i} sentinel.`,
      word_count: 800,
    }));
    const large: ChapterView = {
      ...chapter,
      sections,
      chapter_word_count: SECTIONS * 800,
      total_word_count: SECTIONS * 800,
    };

    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={large} scrollTarget={null} />,
    );

    // First and last section sentinels both present → the chapter rendered whole.
    await screen.findByText("Marker 0 sentinel.", undefined, { timeout: 5000 });
    await screen.findByText(`Marker ${SECTIONS - 1} sentinel.`);
    expect(container.querySelectorAll("[data-section-anchor]")).toHaveLength(
      SECTIONS,
    );
  });
});

describe("ChapterReader highlight load (RD-28)", () => {
  it("fetches the source highlights and paints them into the flow", async () => {
    nav.params = new URLSearchParams();
    const painted: SourceHighlightView = {
      note_id: "n9",
      note_title: "Ada Lovelace wrote the first algorithm",
      has_body: false,
      anchor: S1,
      quote_exact: "Ada Lovelace wrote the first algorithm",
      quote_prefix: "",
      quote_suffix: "",
      status: "active",
    };
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        [`GET ${CHAPTER_URL_RESUME}`]: () => jsonResponse(200, chapter),
        [`GET ${HIGHLIGHTS_URL}`]: () => jsonResponse(200, [painted]),
      }),
    );

    const { container } = render(<ChapterReader sourceId="s1" />);

    // The chapter loaded, the highlights fetch resolved, and its active quote
    // painted in section one (the mark exists only inside the rendered flow).
    await waitFor(() =>
      expect(
        container
          .querySelector("mark.reader-highlight")
          ?.getAttribute("data-note-id"),
      ).toBe("n9"),
    );
    expect(container.querySelector("mark.reader-highlight")?.textContent).toBe(
      "Ada Lovelace wrote the first algorithm",
    );
  });
});

describe("ChapterFlow panel modes (RA-01/02/03/06)", () => {
  it("opens the ask panel when ?panel=ask (RA-01)", async () => {
    nav.params = new URLSearchParams("panel=ask");
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    const panel = screen.getByTestId("reader-panel");
    expect(panel.getAttribute("data-mode")).toBe("ask");
    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
  });

  it("opens the teach panel when ?panel=teach (RA-02)", async () => {
    nav.params = new URLSearchParams("panel=teach");
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    const panel = screen.getByTestId("reader-panel");
    expect(panel.getAttribute("data-mode")).toBe("teach");
    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
  });

  it("renders no panel when the panel param is absent", async () => {
    nav.params = new URLSearchParams();
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(screen.queryByTestId("reader-panel")).toBeNull();
  });

  it("renders no panel for an unknown panel value (edge case)", async () => {
    nav.params = new URLSearchParams("panel=notes");
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(screen.queryByTestId("reader-panel")).toBeNull();
  });

  it("closes the panel via router.replace, preserving the anchor (RA-03)", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}&panel=ask`);
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={S2} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));

    // The panel param is dropped (full reading width restored) but the anchor rides along.
    expect(nav.replace).toHaveBeenCalledWith(
      `/sources/s1/read?anchor=${ENCODED_S2}`,
    );
  });

  it("switches modes via router.replace, preserving the anchor (RA-03)", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}&panel=ask`);
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={S2} />,
    );

    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));

    expect(nav.replace).toHaveBeenCalledWith(
      `/sources/s1/read?anchor=${ENCODED_S2}&panel=teach`,
    );
  });

  it("keeps scroll tracking and highlight painting active with the panel open (RA-06)", async () => {
    nav.params = new URLSearchParams("panel=ask");
    const obs = fakeObserver();
    const painted: SourceHighlightView = {
      note_id: "n3",
      note_title: "Ada Lovelace wrote the first algorithm",
      has_body: false,
      anchor: S1,
      quote_exact: "Ada Lovelace wrote the first algorithm",
      quote_prefix: "",
      quote_suffix: "",
      status: "active",
    };
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        highlights={[painted]}
        observerFactory={obs.factory}
      />,
    );

    // The painted highlight splits the sentence text node, so anchor the render
    // check on the structural heading instead of the painted prose.
    await screen.findByRole("heading", { name: "The First Algorithm" });
    // Reading stays non-modal: the panel is open beside the article, not over it.
    expect(screen.getByTestId("reader-panel")).toBeTruthy();
    // Highlight painting keeps working under the open panel.
    await waitFor(() =>
      expect(container.querySelectorAll("mark.reader-highlight")).toHaveLength(1),
    );
    // Scroll-position tracking still drives live progress with the panel open.
    expect(screen.getByTestId("reading-progress").textContent).toContain("10%");
    obs.emit({ [S1]: false, [S2]: true });
    await waitFor(() =>
      expect(screen.getByTestId("reading-progress").textContent).toContain("40%"),
    );
  });
});

describe("ChapterFlow show in book (RA-13/14)", () => {
  it("scrolls to an in-chapter cited anchor and flashes it, panel still open, no navigation", async () => {
    nav.params = new URLSearchParams("panel=teach");
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    // No target on load, so nothing has scrolled yet.
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();

    // The teach panel asks to show an anchor that lives in the loaded chapter.
    fireEvent.click(screen.getByRole("button", { name: "show-in-chapter" }));

    // It scrolled to the anchor in the flow and flashed its heading; the panel
    // stays open beside the answer and there is no full navigation (push).
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    const flashed = document.querySelector(`[data-section-heading="${S2}"]`);
    expect(flashed?.getAttribute("data-highlight")).toBe("on");
    expect(screen.getByTestId("reader-panel")).toBeTruthy();
    expect(nav.push).not.toHaveBeenCalled();
    // The anchor rides into the URL (with the panel preserved) as a shallow replace.
    expect(nav.replace).toHaveBeenCalledWith(
      `/sources/s1/read?anchor=${ENCODED_S2}&panel=teach`,
    );
  });

  it("navigates to a cited anchor in another chapter, carrying the open panel", async () => {
    nav.params = new URLSearchParams("panel=teach");
    render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");

    // The teach panel asks to show an anchor NOT in the loaded chapter.
    fireEvent.click(screen.getByRole("button", { name: "show-foreign" }));

    // It navigates to that anchor with the panel param preserved; no in-flow scroll.
    expect(nav.push).toHaveBeenCalledWith(
      "/sources/s1/read?anchor=part1%2Fch2.xhtml%23s1&panel=teach",
    );
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(nav.replace).not.toHaveBeenCalled();
  });
});

describe("ChapterFlow selection verbs (RA-17/18)", () => {
  function selectInSection(container: HTMLElement, anchor: string, text: string) {
    selectText(text);
    fireEvent.mouseUp(
      container.querySelector(`[data-section-anchor="${anchor}"]`)!,
    );
  }

  it("hands the ask panel an explain request carrying the quote and anchor", async () => {
    nav.params = new URLSearchParams("panel=ask");
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");

    selectInSection(container, S1, "Ada Lovelace wrote the first algorithm");
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));

    // The ask panel receives an explain request with the verbatim selection quote
    // and the selection's section anchor.
    expect(screen.getByTestId("pending-request").textContent).toBe(
      `explain|Ada Lovelace wrote the first algorithm|${S1}`,
    );
    // The capture popover is dismissed once the verb routes into the panel.
    expect(
      screen.queryByRole("dialog", { name: "Capture highlight" }),
    ).toBeNull();
  });

  it("hands the ask panel an ask-about request when Ask is tapped", async () => {
    nav.params = new URLSearchParams("panel=ask");
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");

    selectInSection(container, S1, "Ada Lovelace wrote the first algorithm");
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByTestId("pending-request").textContent).toBe(
      `ask|Ada Lovelace wrote the first algorithm|${S1}`,
    );
  });

  it("opens the panel in ask mode when a verb is tapped with the panel closed", async () => {
    nav.params = new URLSearchParams();
    const { container } = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(screen.queryByTestId("reader-panel")).toBeNull();

    selectInSection(container, S1, "Ada Lovelace wrote the first algorithm");
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));

    // The reader opens the ask panel via a shallow URL replace (anchor preserved).
    expect(nav.replace).toHaveBeenCalledWith("/sources/s1/read?panel=ask");
    expect(
      screen.queryByRole("dialog", { name: "Capture highlight" }),
    ).toBeNull();
  });
});

describe("ChapterReader cross-chapter jump (RA-13/14)", () => {
  const ENCODED_S1 = "part1%2Fch1.xhtml%23s1";
  const CHAPTER_URL_S1 = `/api/sources/s1/chapter?anchor=${ENCODED_S1}`;
  const FOREIGN_ENC = "part1%2Fch2.xhtml%23s1";
  const CHAPTER_URL_FOREIGN = `/api/sources/s1/chapter?anchor=${FOREIGN_ENC}`;

  const chapterCallsOf = (fetchMock: ReturnType<typeof routedFetch>) => () =>
    fetchMock.mock.calls.filter(([u]) =>
      String(u).startsWith("/api/sources/s1/chapter"),
    ).length;

  it("does not refetch when the anchor changes within the loaded chapter (RA-13)", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S1}`);
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${CHAPTER_URL_S1}`]: () => jsonResponse(200, chapter),
      [`GET ${HIGHLIGHTS_URL}`]: () => jsonResponse(200, []),
    });
    vi.stubGlobal("fetch", fetchMock);
    const chapterCalls = chapterCallsOf(fetchMock);

    const { rerender } = render(<ChapterReader sourceId="s1" />);
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(chapterCalls()).toBe(1);

    // The anchor changes to a section that lives in the SAME loaded chapter.
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);
    rerender(<ChapterReader sourceId="s1" />);

    // The flow scrolls to it in place (its heading flashes); no new chapter load.
    await waitFor(() => {
      const flashed = document.querySelector(`[data-section-heading="${S2}"]`);
      expect(flashed?.getAttribute("data-highlight")).toBe("on");
    });
    expect(chapterCalls()).toBe(1);
  });

  it("refetches when the anchor changes to a section outside the loaded chapter (RA-14)", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);
    const foreignChapter: ChapterView = {
      ...chapter,
      chapter_title: "Chapter Two",
      chapter_anchor: "part1/ch2.xhtml#s1",
      prev_anchor: S1,
      next_anchor: null,
      sections: [
        {
          anchor: "part1/ch2.xhtml#s1",
          title: "The Second Chapter",
          section_path: ["Chapter Two", "Onward"],
          markdown: "## Onward\n\nThe second chapter opens here.",
          word_count: 200,
        },
      ],
    };
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${CHAPTER_URL_S2}`]: () => jsonResponse(200, chapter),
      [`GET ${CHAPTER_URL_FOREIGN}`]: () => jsonResponse(200, foreignChapter),
      [`GET ${HIGHLIGHTS_URL}`]: () => jsonResponse(200, []),
    });
    vi.stubGlobal("fetch", fetchMock);
    const chapterCalls = chapterCallsOf(fetchMock);

    const { rerender } = render(<ChapterReader sourceId="s1" />);
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    expect(chapterCalls()).toBe(1);

    // The anchor changes to a section in ANOTHER chapter — a reload is required.
    nav.params = new URLSearchParams(`anchor=${FOREIGN_ENC}`);
    rerender(<ChapterReader sourceId="s1" />);

    await screen.findByText("The second chapter opens here.");
    expect(chapterCalls()).toBe(2);
  });
});

describe("ChapterReader panel param (RA-03)", () => {
  it("does not refetch the chapter when only the panel param changes", async () => {
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}`);
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      [`GET ${CHAPTER_URL_S2}`]: () => jsonResponse(200, chapter),
      [`GET ${HIGHLIGHTS_URL}`]: () => jsonResponse(200, []),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<ChapterReader sourceId="s1" />);
    await screen.findByText("Ada Lovelace wrote the first algorithm.");
    const chapterCalls = () =>
      fetchMock.mock.calls.filter(([u]) =>
        String(u).startsWith("/api/sources/s1/chapter"),
      ).length;
    expect(chapterCalls()).toBe(1);

    // The panel opens on the same anchor — a shallow URL change, not a new load.
    nav.params = new URLSearchParams(`anchor=${ENCODED_S2}&panel=ask`);
    rerender(<ChapterReader sourceId="s1" />);

    await screen.findByTestId("reader-panel");
    expect(chapterCalls()).toBe(1);
  });
});

describe("ChapterFlow progress (RD-11)", () => {
  it("shows live book-percent and chapter minutes-left that update as the observed section changes", async () => {
    const obs = fakeObserver();
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        observerFactory={obs.factory}
      />,
    );
    await screen.findByText("Ada Lovelace wrote the first algorithm.");

    // At the chapter top (nothing observed yet): (words_before 100 + 0) / 1000 =
    // 10%; minutes-left = ceil((500 - 0) / 220) = 3.
    const progress = screen.getByTestId("reading-progress");
    expect(progress.textContent).toContain("10%");
    expect(progress.textContent).toContain("3 min");

    // Scroll so section two is the topmost visible (section one scrolled above).
    obs.emit({ [S1]: false, [S2]: true });

    // words read in chapter = section one's 300 → (100 + 300) / 1000 = 40%;
    // minutes-left = ceil((500 - 300) / 220) = 1.
    await waitFor(() =>
      expect(screen.getByTestId("reading-progress").textContent).toContain(
        "40%",
      ),
    );
    expect(screen.getByTestId("reading-progress").textContent).toContain(
      "1 min",
    );
  });
});

describe("ChapterFlow create card (CAP-01/08)", () => {
  const SUGGEST_URL = "/api/sources/s1/cards/suggestions";
  const CARDS_URL = "/api/sources/s1/cards";
  const QUOTE = "Ada Lovelace wrote the first algorithm";

  /** The capture response the card flow reads the new anchor's id from. */
  const capturedNote = {
    id: "n1",
    title: QUOTE,
    body_markdown: "",
    tags: [],
    anchors: [
      {
        id: "a1",
        source_id: "s1",
        source_title: "Ready Book",
        anchor: S1,
        section_path: ["Chapter One", "Beginnings"],
        block_ordinal: 0,
        start_offset: 0,
        end_offset: 37,
        quote_exact: QUOTE,
        quote_prefix: "## Beginnings ",
        quote_suffix: ".",
        status: "active",
      },
    ],
    created_at: "now",
    updated_at: "now",
  };

  const suggestion = {
    item_type: "free_recall",
    question: "Who wrote the first algorithm?",
    answer: "Ada Lovelace",
    anchor_quote: QUOTE,
  };

  const savedCard = {
    id: "c1",
    source_id: "s1",
    origin: "highlight",
    note_anchor_id: "a1",
    item_type: "free_recall",
    question: "Who wrote the first algorithm?",
    answer: "Ada Lovelace",
    citation: { section_path: ["Chapter One"], anchor: S1, source_excerpt: QUOTE },
    status: "active",
    created_at: "now",
    updated_at: "now",
  };

  /** Render the flow and raise the popover on a selection in section one. */
  function renderAndSelect() {
    const view = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    selectText(QUOTE);
    fireEvent.mouseUp(
      view.container.querySelector(`[data-section-anchor="${S1}"]`)!,
    );
    return view;
  }

  const callsTo = (fetchMock: ReturnType<typeof routedFetch>, url: string) => () =>
    fetchMock.mock.calls.filter(([u]) => u === url).length;

  it("reuses the card flow's highlight instead of capturing the passage twice", async () => {
    // Create card saves the highlight as its first step. Pressing Highlight after it
    // must not write a second identical highlight for the same selection.
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [suggestion] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAndSelect();

    fireEvent.click(screen.getByRole("button", { name: "Create card" }));
    await screen.findByText("Who wrote the first algorithm?");
    expect(callsTo(fetchMock, HIGHLIGHTS_URL)()).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Capture highlight" })).toBeNull(),
    );
    // Still one highlight for one passage.
    expect(callsTo(fetchMock, HIGHLIGHTS_URL)()).toBe(1);
  });

  it("opens the note the card flow already made rather than making another", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [suggestion] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAndSelect();

    fireEvent.click(screen.getByRole("button", { name: "Create card" }));
    await screen.findByText("Who wrote the first algorithm?");

    fireEvent.click(screen.getByRole("button", { name: "Note" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes/n1"));
    expect(callsTo(fetchMock, HIGHLIGHTS_URL)()).toBe(1);
  });

  it("starts a fresh card flow when the student selects a different passage", async () => {
    // Without the reset, the second selection would generate cards against the first
    // passage's anchor — cards attributed to text the student did not choose.
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [suggestion] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = renderAndSelect();

    fireEvent.click(screen.getByRole("button", { name: "Create card" }));
    await screen.findByText("Who wrote the first algorithm?");

    // A new selection in another section: the previous suggestions must be gone.
    selectText("Babbage designed the analytical engine");
    fireEvent.mouseUp(
      view.container.querySelector(`[data-section-anchor="${S2}"]`)!,
    );

    await waitFor(() =>
      expect(screen.queryByText("Who wrote the first algorithm?")).toBeNull(),
    );

    // Creating a card now captures the NEW passage rather than reusing the old anchor.
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));
    await waitFor(() => expect(callsTo(fetchMock, HIGHLIGHTS_URL)()).toBe(2));
    const second = fetchMock.mock.calls.filter(([u]) => u === HIGHLIGHTS_URL)[1];
    expect(JSON.parse((second[1] as RequestInit).body as string).quote_exact).toBe(
      "Babbage designed the analytical engine",
    );
  });

  it("captures the highlight first, then asks for suggestions on the anchor it produced", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [suggestion] }),
      [`POST ${CARDS_URL}`]: () => jsonResponse(201, savedCard),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAndSelect();
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));

    // The suggestion request carries the anchor id the capture just minted —
    // proof the reader sequenced the two single-purpose calls rather than
    // expecting one endpoint to do both.
    await waitFor(() => expect(callsTo(fetchMock, SUGGEST_URL)()).toBe(1));
    const suggest = fetchMock.mock.calls.find(([u]) => u === SUGGEST_URL)!;
    expect(JSON.parse((suggest[1] as RequestInit).body as string)).toEqual({
      note_anchor_id: "a1",
    });

    // The chip renders and accepting it writes the card against the same anchor.
    await screen.findByText("Who wrote the first algorithm?");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(callsTo(fetchMock, CARDS_URL)()).toBe(1));
    const accept = fetchMock.mock.calls.find(([u]) => u === CARDS_URL)!;
    expect(JSON.parse((accept[1] as RequestInit).body as string)).toEqual({
      note_anchor_id: "a1",
      item_type: "free_recall",
      question: "Who wrote the first algorithm?",
      answer: "Ada Lovelace",
    });
    // The whole selection flow closes once the last suggestion is resolved.
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Capture highlight" }),
      ).toBeNull(),
    );
  });

  it("keeps the highlight and retries only generation when suggestions fail", async () => {
    let suggestAttempt = 0;
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => {
        suggestAttempt += 1;
        return suggestAttempt === 1
          ? jsonResponse(502, { detail: "The card generator is unavailable." })
          : jsonResponse(200, { suggestions: [suggestion] });
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const captures = callsTo(fetchMock, HIGHLIGHTS_URL);

    renderAndSelect();
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));

    // Generation failed, but the highlight was already saved and stays saved.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("The card generator is unavailable.");
    expect(captures()).toBe(1);

    // Pressing the verb again retries generation ONLY — capturing the same
    // passage twice would leave the student with a duplicate highlight.
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));

    await screen.findByText("Who wrote the first algorithm?");
    expect(suggestAttempt).toBe(2);
    expect(captures()).toBe(1);
  });

  it("shows the reload prompt when the passage moved under the selection (409)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
        [`POST ${SUGGEST_URL}`]: () =>
          jsonResponse(409, { detail: "That passage changed." }),
      }),
    );

    renderAndSelect();
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));

    // The same reload message the highlight capture uses for its own 409.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/reload the page/i);
  });

  it("reports an empty batch as no cards for this passage, not as a failure", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
        [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [] }),
      }),
    );

    renderAndSelect();
    fireEvent.click(screen.getByRole("button", { name: "Create card" }));

    expect(await screen.findByText("No cards for this passage.")).toBeTruthy();
    // Nothing is announced as an error; the highlight was still captured.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ChapterFlow margin rail (CAP-18/21/24)", () => {
  const FOREIGN = "part1/ch2.xhtml#s1";

  function railHighlight(
    over: Partial<SourceHighlightView>,
  ): SourceHighlightView {
    return {
      note_id: "n1",
      note_title: "Ada Lovelace wrote the first algorithm",
      has_body: false,
      anchor: S1,
      quote_exact: "Ada Lovelace wrote the first algorithm",
      quote_prefix: "",
      quote_suffix: "",
      status: "active",
      ...over,
    };
  }

  it("shows the loaded chapter's highlights and drops a highlight from another chapter", async () => {
    nav.params = new URLSearchParams();
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        highlights={[
          railHighlight({ note_id: "n1", anchor: S1 }),
          railHighlight({
            note_id: "n2",
            anchor: FOREIGN,
            quote_exact: "Babbage designed the analytical engine",
          }),
        ]}
      />,
    );

    await screen.findByTestId("margin-rail");
    // The reader loads every highlight on the source in one call; the rail is
    // scoped to the chapter on screen, so the next chapter's does not appear.
    const quotes = screen
      .getAllByTestId("rail-quote")
      .map((node) => node.textContent);
    expect(quotes).toEqual(["Ada Lovelace wrote the first algorithm"]);
  });

  it("scrolls to and flashes the section a rail entry points at", async () => {
    nav.params = new URLSearchParams();
    const scrollIntoView = vi.fn();
    const { container } = render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        highlights={[railHighlight({ anchor: S2 })]}
      />,
    );
    await screen.findByTestId("margin-rail");
    const target = container.querySelector<HTMLElement>(
      `[data-section-anchor="${S2}"]`,
    )!;
    target.scrollIntoView = scrollIntoView;

    fireEvent.click(screen.getByTestId("rail-entry").querySelector("button")!);

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "start",
    });
    // The jumped-to heading flashes, exactly as a citation jump does.
    await waitFor(() =>
      expect(
        container
          .querySelector(`[data-section-heading="${S2}"]`)
          ?.getAttribute("data-highlight"),
      ).toBe("on"),
    );
    // The URL anchor keeps step so the position stays shareable.
    expect(nav.replace).toHaveBeenCalledWith(
      `/sources/s1/read?anchor=${ENCODED_S2}`,
    );
  });

  it("hides the rail while the ask panel is open (AD-139)", async () => {
    nav.params = new URLSearchParams("panel=ask");
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        highlights={[railHighlight({})]}
      />,
    );

    // The panel wins the right-hand column: the rail is not rendered at all.
    await screen.findByTestId("reader-panel");
    expect(screen.queryByTestId("margin-rail")).toBeNull();
  });

  it("renders the rail again once the panel is closed", async () => {
    nav.params = new URLSearchParams();
    render(
      <ChapterFlow
        sourceId="s1"
        csrf="csrf-xyz"
        chapter={chapter}
        scrollTarget={null}
        highlights={[railHighlight({})]}
      />,
    );

    expect(await screen.findByTestId("margin-rail")).toBeTruthy();
    expect(screen.queryByTestId("reader-panel")).toBeNull();
  });
});

describe("ChapterFlow capture shortcuts (CAP-28/29/32)", () => {
  const SUGGEST_URL = "/api/sources/s1/cards/suggestions";
  const QUOTE = "Ada Lovelace wrote the first algorithm";

  const capturedNote = {
    id: "n1",
    title: QUOTE,
    body_markdown: "",
    tags: [],
    anchors: [
      {
        id: "a1",
        source_id: "s1",
        source_title: "Ready Book",
        anchor: S1,
        section_path: ["Chapter One", "Beginnings"],
        block_ordinal: 0,
        start_offset: 0,
        end_offset: 37,
        quote_exact: QUOTE,
        quote_prefix: "## Beginnings ",
        quote_suffix: ".",
        status: "active",
      },
    ],
    created_at: "now",
    updated_at: "now",
  };

  /** Writes to the capture endpoint only — the TOC's own reads are not actions. */
  const captures = (fetchMock: ReturnType<typeof routedFetch>) =>
    fetchMock.mock.calls.filter(([url]) => url === HIGHLIGHTS_URL).length;

  /** Render the flow; `select` raises the popover on a selection in section one. */
  function renderFlow() {
    const view = render(
      <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
    );
    return {
      ...view,
      select() {
        selectText(QUOTE);
        fireEvent.mouseUp(
          view.container.querySelector(`[data-section-anchor="${S1}"]`)!,
        );
      },
    };
  }

  function pressKey(
    key: string,
    target: EventTarget = window,
    init: KeyboardEventInit = {},
  ) {
    target.dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }),
    );
  }

  it("captures the selection on the highlight key, exactly as the verb does", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = renderFlow();
    view.select();
    act(() => pressKey("h"));

    await waitFor(() => expect(captures(fetchMock)).toBe(1));
    const call = fetchMock.mock.calls.find(([url]) => url === HIGHLIGHTS_URL)!;
    expect(JSON.parse((call[1] as RequestInit).body as string).quote_exact).toBe(
      QUOTE,
    );
  });

  it("starts the card flow on the card key", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = renderFlow();
    view.select();
    act(() => pressKey("c"));

    expect(await screen.findByText("No cards for this passage.")).toBeTruthy();
  });

  it("does nothing on a bare key press with no selection open", async () => {
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    renderFlow();
    // No popover is up, so there is no passage the key could act on — and a
    // write the student has no on-screen evidence of must never happen.
    act(() => {
      pressKey("h");
      pressKey("c");
    });

    expect(captures(fetchMock)).toBe(0);
    expect(screen.queryByRole("dialog", { name: "Capture highlight" })).toBeNull();
  });

  it("ignores the highlight key typed into a text field", async () => {
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    const view = renderFlow();
    view.select();
    // The popover is open, so the shortcut is armed — but the student is typing.
    const textarea = document.body.appendChild(document.createElement("textarea"));
    act(() => pressKey("h", textarea));

    expect(captures(fetchMock)).toBe(0);
    textarea.remove();
  });

  it("ignores the highlight key while a modifier is held, and never binds b", async () => {
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    const view = renderFlow();
    view.select();
    act(() => {
      pressKey("h", window, { ctrlKey: true });
      // The sidebar owns Cmd/Ctrl+B; the reader must never claim `b` at all.
      pressKey("b");
      pressKey("b", window, { ctrlKey: true });
    });

    expect(captures(fetchMock)).toBe(0);
  });
});
