// @vitest-environment jsdom

/**
 * E4 gate (budget) — the capture gestures held to a measured action count
 * (CAP-34/35/36, AD-142).
 *
 * "Low friction" is a claim until something counts. Each test below performs
 * *exactly* the budgeted number of pointer actions through the `pointer` counter
 * and then asserts the outcome actually happened, so a change that inserts a step
 * — a confirm dialog, an extra menu, a mandatory reveal before the pin — fails
 * here twice over: the outcome never arrives, and the recorded count no longer
 * matches the budget.
 *
 * The budget counts clicks, not cognitive load, and is honestly labelled as the
 * partial proxy it is (AD-142). What it defends is the shape of each path:
 *
 * - highlight, from a selection the student already made: 1 action
 * - card, from that same selection: 2 actions (invoke, accept)
 * - review jump-back to the passage: 1 action
 *
 * Making the selection is not counted in the first two — the budget begins from
 * "an existing selection", which is the premise of the acceptance criteria.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChapterFlow } from "../app/components/chapter-reader";
import { ReviewScreen } from "../app/components/review-screen";
import { readUrl } from "../app/lib/read-url";
import type { ChapterView } from "../app/lib/reading";

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

function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

/**
 * The meter. Every pointer action in a budgeted path goes through `click`, and
 * nothing else in the path may click, so `count` is the path's real cost.
 */
function actionMeter() {
  let count = 0;
  return {
    click(element: Element) {
      count += 1;
      fireEvent.click(element);
    },
    get count() {
      return count;
    },
  };
}

const S1 = "part1/ch1.xhtml#s1";
const QUOTE = "Ada Lovelace wrote the first algorithm";
const HIGHLIGHTS_URL = "/api/sources/s1/highlights";
const SUGGEST_URL = "/api/sources/s1/cards/suggestions";
const CARDS_URL = "/api/sources/s1/cards";

const chapter: ChapterView = {
  chapter_title: "Chapter One",
  chapter_anchor: S1,
  chapter_index: 0,
  chapter_count: 1,
  prev_anchor: null,
  next_anchor: null,
  words_before_chapter: 0,
  chapter_word_count: 300,
  total_word_count: 300,
  sections: [
    {
      anchor: S1,
      title: "The First Algorithm",
      section_path: ["Chapter One", "Beginnings"],
      markdown: "## Beginnings\n\nAda Lovelace wrote the first algorithm.",
      word_count: 300,
    },
  ],
  reading_position: null,
};

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

/** Stub `window.getSelection` to return `text` as the current selection. */
function selectText(text: string) {
  window.getSelection = () =>
    ({
      toString: () => text,
      rangeCount: 0,
      getRangeAt: () => ({ getBoundingClientRect: () => undefined }),
    }) as unknown as Selection;
}

/**
 * The reader with a passage already selected — the state both capture budgets
 * start from. Raising the popover is part of making the selection, so it happens
 * outside the meter.
 */
function readerWithSelection() {
  const view = render(
    <ChapterFlow sourceId="s1" csrf="csrf-xyz" chapter={chapter} scrollTarget={null} />,
  );
  act(() => {
    selectText(QUOTE);
    fireEvent.mouseUp(
      view.container.querySelector(`[data-section-anchor="${S1}"]`)!,
    );
  });
  return view;
}

const callsTo = (fetchMock: ReturnType<typeof routedFetch>, url: string) =>
  fetchMock.mock.calls.filter(([u]) => u === url).length;

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  vi.restoreAllMocks();
});

describe("Friction budget: highlight (CAP-34)", () => {
  it("costs one pointer action from an existing selection", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
    });
    vi.stubGlobal("fetch", fetchMock);
    const meter = actionMeter();

    readerWithSelection();
    meter.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() => expect(callsTo(fetchMock, HIGHLIGHTS_URL)).toBe(1));
    expect(meter.count).toBe(1);
  });
});

describe("Friction budget: card (CAP-35)", () => {
  it("costs two pointer actions from an existing selection: invoke, accept", async () => {
    const fetchMock = routedFetch({
      [`POST ${HIGHLIGHTS_URL}`]: () => jsonResponse(201, capturedNote),
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [suggestion] }),
      [`POST ${CARDS_URL}`]: () => jsonResponse(201, savedCard),
    });
    vi.stubGlobal("fetch", fetchMock);
    const meter = actionMeter();

    readerWithSelection();

    // 1 — invoke. The capture and the generation are sequenced for the student.
    meter.click(screen.getByRole("button", { name: "Create card" }));
    await screen.findByText("Who wrote the first algorithm?");

    // 2 — accept. No confirm step, no separate save.
    meter.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(callsTo(fetchMock, CARDS_URL)).toBe(1));
    expect(meter.count).toBe(2);
    // The passage really did become a scheduled card, not just a request.
    expect(callsTo(fetchMock, HIGHLIGHTS_URL)).toBe(1);
  });
});

describe("Friction budget: review jump-back (CAP-36)", () => {
  it("costs one pointer action, with the pin reachable before any interaction", async () => {
    const dueCard = {
      id: "i1",
      source_id: "s1",
      source_title: "Ready Book",
      item_type: "cloze",
      question: "Ada wrote the first ____.",
      answer: "algorithm",
      citation: {
        section_path: ["Chapter 1"],
        anchor: S1,
        source_excerpt: QUOTE,
      },
      provenance: null,
      status: "active",
      due: "2026-07-16T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () =>
          jsonResponse(200, {
            id: "u1",
            email: "a@b.c",
            created_at: "now",
            csrf_token: "csrf-xyz",
          }),
        "GET /api/reviews/due?source_id=s1": () =>
          jsonResponse(200, { items: [dueCard], total_due: 1 }),
      }),
    );
    const meter = actionMeter();

    render(<ReviewScreen sourceId="s1" />);
    await screen.findByTestId("question");

    // Zero actions in, the way back is already on screen — a card the student
    // just failed must not cost a reveal before it can become a re-read.
    const pin = screen.getByRole("link", { name: "Open in book" });
    expect(pin.getAttribute("href")).toBe(readUrl("s1", S1));

    meter.click(pin);

    expect(meter.count).toBe(1);
  });
});
