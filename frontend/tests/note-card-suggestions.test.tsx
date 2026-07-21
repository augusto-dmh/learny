// @vitest-environment jsdom

/**
 * T12 gate (component) — the note promotion panel (NL-08, NL-15).
 *
 * "Add to review" generates candidates grounded in the note body and raises them as
 * chips; Accept promotes one to a scheduled card, Edit rewrites it so the reader's
 * text is what reaches the server, and Discard drops it with no request at all. A QC
 * batch that grounded nothing reads as an outcome ("no cards could be grounded"),
 * not an error; a generation failure reads as a retryable alert. The panel keeps an
 * honest count of the note's review cards across re-promotion — an idempotent
 * re-accept of identical text returns the same card and never inflates the count.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NoteCardSuggestions } from "../app/components/notes/note-card-suggestions";
import type { Card, CardSuggestion } from "../app/lib/cards";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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

const SUGGEST_URL = "/api/notes/n1/cards/suggest";
const CARDS_URL = "/api/notes/n1/cards";

const first: CardSuggestion = {
  item_type: "free_recall",
  question: "What schedules reviews?",
  answer: "Spaced repetition",
  anchor_quote: "Spaced repetition schedules reviews",
};

const second: CardSuggestion = {
  item_type: "cloze",
  question: "____ schedules reviews.",
  answer: "Spaced repetition",
  anchor_quote: "Spaced repetition schedules reviews",
};

const noteCard: Card = {
  id: "nc1",
  source_id: null,
  origin: "note",
  note_anchor_id: null,
  item_type: "free_recall",
  question: "What schedules reviews?",
  answer: "Spaced repetition",
  citation: { section_path: [], anchor: "", source_excerpt: "Spaced repetition schedules reviews" },
  status: "active",
  created_at: "now",
  updated_at: "now",
};

function renderPanel() {
  return render(<NoteCardSuggestions noteId="n1" csrf="csrf-xyz" />);
}

/** The chip whose visible text contains `text`. */
function chipWith(text: string): HTMLElement {
  const chips = screen.getAllByTestId("note-card-suggestion");
  const found = chips.find((chip) => chip.textContent?.includes(text));
  if (!found) throw new Error(`no chip containing: ${text}`);
  return found;
}

describe("NoteCardSuggestions promote (NL-08)", () => {
  it("makes no request until the reader asks for suggestions", () => {
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    // The panel is idle on mount — nothing generated, nothing persisted.
    expect(screen.getByRole("button", { name: "Add to review" })).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("note-card-suggestion")).toBeNull();
  });

  it("suggests, edits, and promotes the reader's own text (happy path)", async () => {
    let acceptBody: unknown = null;
    const fetchMock = routedFetch({
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [first, second] }),
      [`POST ${CARDS_URL}`]: (init) => {
        acceptBody = JSON.parse(init.body as string);
        return jsonResponse(201, noteCard);
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));

    // Both candidates surface as chips.
    await waitFor(() =>
      expect(screen.getAllByTestId("note-card-suggestion")).toHaveLength(2),
    );

    const chip = chipWith("What schedules reviews?");
    fireEvent.click(within(chip).getByRole("button", { name: "Edit" }));
    fireEvent.change(within(chip).getByLabelText("Question"), {
      target: { value: "What paces reviews over time?" },
    });
    fireEvent.click(within(chip).getByRole("button", { name: "Accept" }));

    // The reader's edit reached the server, not the generated text.
    await waitFor(() => expect(acceptBody).not.toBeNull());
    expect(acceptBody).toEqual({
      item_type: "free_recall",
      question: "What paces reviews over time?",
      answer: "Spaced repetition",
    });

    // The promoted chip leaves; the untouched candidate stays offered; the count shows.
    await waitFor(() =>
      expect(screen.getAllByTestId("note-card-suggestion")).toHaveLength(1),
    );
    expect(screen.getByTestId("note-card-count").textContent).toContain(
      "1 card in review from this note",
    );
  });

  it("discards a candidate with no request at all", async () => {
    const fetchMock = routedFetch({
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [first, second] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));
    await waitFor(() =>
      expect(screen.getAllByTestId("note-card-suggestion")).toHaveLength(2),
    );

    fireEvent.click(
      within(chipWith("What schedules reviews?")).getByRole("button", {
        name: "Discard",
      }),
    );

    // Only the suggest call happened — a discard never posts a card.
    await waitFor(() =>
      expect(screen.getAllByTestId("note-card-suggestion")).toHaveLength(1),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("What schedules reviews?")).toBeNull();
  });
});

describe("NoteCardSuggestions empty QC (NL-08)", () => {
  it("reads a grounded-nothing batch as an outcome, not an error", async () => {
    const fetchMock = routedFetch({
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));

    expect(
      await screen.findByText("No cards could be grounded in this note."),
    ).toBeTruthy();
    // Not an error state: nothing is announced as an alert.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("note-card-suggestion")).toBeNull();
  });
});

describe("NoteCardSuggestions failure", () => {
  it("shows a readable, retryable error on a generation provider failure", async () => {
    let attempt = 0;
    const fetchMock = routedFetch({
      [`POST ${SUGGEST_URL}`]: () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse(502, { detail: "The card generator is unavailable." })
          : jsonResponse(200, { suggestions: [first] });
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("The card generator is unavailable.");

    // The action is retryable in place: a second attempt clears the error and lists.
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));
    await waitFor(() =>
      expect(screen.getByTestId("note-card-suggestion")).toBeTruthy(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("NoteCardSuggestions re-promotion count (NL-15)", () => {
  it("keeps the count honest when the same text is re-promoted", async () => {
    const fetchMock = routedFetch({
      [`POST ${SUGGEST_URL}`]: () => jsonResponse(200, { suggestions: [first] }),
      // The first promote creates the card (201); a re-promote of the same text is
      // deduped server-side and answers 200 with the very same card.
      [`POST ${CARDS_URL}`]: (init) => {
        const seen = (fetchMock.mock.calls as unknown[][]).filter(
          ([url]) => url === CARDS_URL,
        ).length;
        return jsonResponse(seen === 1 ? 201 : 200, noteCard);
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    // First promotion: suggest → accept → count 1.
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));
    await screen.findByTestId("note-card-suggestion");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() =>
      expect(screen.getByTestId("note-card-count").textContent).toContain(
        "1 card in review from this note",
      ),
    );

    // Re-promotion: suggest the same note again, accept the identical text.
    fireEvent.click(screen.getByRole("button", { name: "Add to review" }));
    await screen.findByTestId("note-card-suggestion");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    // The dedup is surfaced and the count did NOT double — still one card.
    expect(
      await screen.findByText(/already in review/i),
    ).toBeTruthy();
    expect(screen.getByTestId("note-card-count").textContent).toContain(
      "1 card in review from this note",
    );
  });
});
