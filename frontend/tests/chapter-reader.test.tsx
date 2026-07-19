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
