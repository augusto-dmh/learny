/**
 * B1 (RD-01/07/28 client) — the reading client talks to the chapter, reading-
 * position, and highlights routes through the same-origin proxy.
 *
 * Verifies getChapter GETs `/api/sources/{id}/chapter[?anchor=<enc>]` with the
 * anchor `encodeURIComponent`-encoded exactly once (and omits the query entirely
 * when resuming with a null anchor), parses the `ChapterView` on 200, returns a
 * typed `not_found` result on 404 (never throwing — the reader renders it), and
 * throws on other non-OK responses; saveReadingPosition PUTs the anchor body with
 * the CSRF header; listHighlights parses the array; and minutesLeft rounds up at
 * 220 wpm with a zero floor. No real network — `fetchImpl` is injected.
 */

import { describe, expect, it, vi } from "vitest";

import {
  getChapter,
  listHighlights,
  minutesLeft,
  saveReadingPosition,
  WORDS_PER_MINUTE,
  type ChapterView,
  type ReadingPositionView,
  type SourceHighlightView,
} from "../app/lib/reading";

// A real anchor: `href` path (`/`) plus fragment (`#`) — both reserved characters.
const ANCHOR = "text/ch1.xhtml#s2";

const chapter: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: "text/ch1.xhtml#s1",
  chapter_index: 0,
  chapter_count: 3,
  prev_anchor: null,
  next_anchor: "text/ch2.xhtml#s1",
  words_before_chapter: 0,
  chapter_word_count: 440,
  total_word_count: 1320,
  sections: [
    {
      anchor: "text/ch1.xhtml#s1",
      title: "Opening",
      section_path: ["Chapter One", "Opening"],
      markdown: "## Opening\n\nBody.",
      word_count: 220,
    },
    {
      anchor: ANCHOR,
      title: "Section Two",
      section_path: ["Chapter One", "Section Two"],
      markdown: "## Section Two\n\nMore body.",
      word_count: 220,
    },
  ],
  reading_position: { anchor: ANCHOR, percent: 16.67, updated_at: "2026-07-19T00:00:00Z" },
};

const position: ReadingPositionView = {
  anchor: ANCHOR,
  percent: 16.67,
  updated_at: "2026-07-19T00:00:00Z",
};

const highlights: SourceHighlightView[] = [
  {
    note_id: "n1",
    note_title: "More body",
    has_body: false,
    anchor: ANCHOR,
    quote_exact: "More body",
    quote_prefix: "## Section Two ",
    quote_suffix: ".",
    status: "active",
  },
];

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fetchMockFn(
  impl: (...args: [string, RequestInit]) => Promise<Response>,
) {
  return vi.fn<(...args: [string, RequestInit]) => Promise<Response>>(impl);
}

describe("getChapter (RD-01)", () => {
  it("GETs the chapter with the anchor URL-encoded exactly once and parses the view", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, chapter));

    const result = await getChapter(
      "s1",
      ANCHOR,
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "found", chapter });
    const [url, init] = fetchMock.mock.calls[0];
    // Encoded once: `/`→`%2F`, `#`→`%23`. Not double-encoded (`%252F`).
    expect(url).toBe("/api/sources/s1/chapter?anchor=text%2Fch1.xhtml%23s2");
    expect(url).not.toContain("%25");
    expect(new URL(`http://x${url}`).searchParams.get("anchor")).toBe(ANCHOR);
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("omits the anchor query entirely when resuming with a null anchor", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, chapter));

    await getChapter("s1", null, fetchMock as unknown as typeof fetch);

    const [url] = fetchMock.mock.calls[0];
    // No query string at all — the server resumes the stored position.
    expect(url).toBe("/api/sources/s1/chapter");
  });

  it("returns a typed not-found result on 404 without throwing", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Chapter not found." }),
    );

    const result = await getChapter(
      "s1",
      ANCHOR,
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "not_found" });
  });

  it("throws a readable error when unauthenticated (401)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    await expect(
      getChapter("s1", ANCHOR, fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Not authenticated.");
  });
});

describe("saveReadingPosition (RD-07)", () => {
  it("PUTs the anchor body with the CSRF header and parses the stored view", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, position));

    const result = await saveReadingPosition(
      "s1",
      ANCHOR,
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(position);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/reading-position");
    expect(init.method).toBe("PUT");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual({ anchor: ANCHOR });
  });

  it("throws on a non-OK response so the reader can retry on the next idle", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Anchor not found." }),
    );

    await expect(
      saveReadingPosition(
        "s1",
        ANCHOR,
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Anchor not found.");
  });
});

describe("listHighlights (RD-28)", () => {
  it("GETs the highlights and parses the array", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, highlights));

    const result = await listHighlights(
      "s1",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(highlights);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/highlights");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("throws a readable error on a non-OK response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Source not found." }),
    );

    await expect(
      listHighlights("s1", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Source not found.");
  });
});

describe("minutesLeft (RD-11)", () => {
  it("rounds partial minutes up at 220 wpm", () => {
    expect(WORDS_PER_MINUTE).toBe(220);
    // Exactly one minute stays one; one word past it rolls to two.
    expect(minutesLeft(220)).toBe(1);
    expect(minutesLeft(221)).toBe(2);
    expect(minutesLeft(1)).toBe(1);
  });

  it("floors at zero for a fully-read (or over-read) chapter", () => {
    expect(minutesLeft(0)).toBe(0);
    expect(minutesLeft(-5)).toBe(0);
  });
});
