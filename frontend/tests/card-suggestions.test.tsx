// @vitest-environment jsdom

/**
 * D2 (component) — the suggestion chips resolve one candidate at a time (CAP-05..08).
 *
 * Accept persists exactly one card and reports it up; Edit rewrites the chip inline
 * so the text that reaches the server is the student's, not the generator's; Discard
 * is purely local and issues no request at all — the routed fetch throws on any
 * unregistered call, so a stray POST would fail the test rather than pass silently.
 * A failed Accept renders inline and the chip survives to be retried, and an empty
 * candidate list reads as "no cards for this passage" rather than as an error.
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

import { CardSuggestions } from "../app/components/notes/card-suggestions";
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

const CARDS_URL = "/api/sources/s1/cards";

const first: CardSuggestion = {
  item_type: "free_recall",
  question: "Who wrote the first algorithm?",
  answer: "Ada Lovelace",
  anchor_quote: "Ada Lovelace wrote the first algorithm",
};

const second: CardSuggestion = {
  item_type: "cloze",
  question: "____ wrote the first algorithm.",
  answer: "Ada Lovelace",
  anchor_quote: "Ada Lovelace wrote the first algorithm",
};

const saved: Card = {
  id: "c1",
  source_id: "s1",
  origin: "highlight",
  note_anchor_id: "a1",
  item_type: "free_recall",
  question: "Who wrote the first algorithm?",
  answer: "Ada Lovelace",
  citation: {
    section_path: ["Chapter One"],
    anchor: "part1/ch1.xhtml#s1",
    source_excerpt: "Ada Lovelace wrote the first algorithm",
  },
  status: "active",
  created_at: "now",
  updated_at: "now",
};

function renderChips(
  props: Partial<React.ComponentProps<typeof CardSuggestions>> = {},
) {
  return render(
    <CardSuggestions
      sourceId="s1"
      noteAnchorId="a1"
      csrf="csrf-xyz"
      suggestions={[first, second]}
      {...props}
    />,
  );
}

/** The chip whose visible text contains `text`. */
function chipWith(text: string): HTMLElement {
  const chips = screen.getAllByTestId("card-suggestion");
  const found = chips.find((chip) => chip.textContent?.includes(text));
  if (!found) throw new Error(`no chip containing: ${text}`);
  return found;
}

describe("CardSuggestions accept (CAP-05)", () => {
  it("persists the accepted candidate once and reports the created card up", async () => {
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: () => jsonResponse(201, saved),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    renderChips({ onAccepted });

    fireEvent.click(
      within(chipWith("Who wrote the first algorithm?")).getByRole("button", {
        name: "Accept",
      }),
    );

    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith(saved));
    // Exactly one card was written — accepting one chip never touches the others.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      note_anchor_id: "a1",
      item_type: "free_recall",
      question: "Who wrote the first algorithm?",
      answer: "Ada Lovelace",
    });
    // The resolved chip leaves the row; the untouched candidate stays offered.
    await waitFor(() =>
      expect(screen.getAllByTestId("card-suggestion")).toHaveLength(1),
    );
    expect(screen.getByText("____ wrote the first algorithm.")).toBeTruthy();
  });

  it("treats an idempotent re-accept (200) as success, not as a failure to retry", async () => {
    // A double submit answers 200 with the card that already exists. The chip must
    // resolve exactly as it would on a 201 — no error, and no second POST.
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: () => jsonResponse(200, saved),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    renderChips({ suggestions: [first], onAccepted });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith(saved));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports every accepted card when the student keeps more than one", async () => {
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: () => jsonResponse(201, saved),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    const onDismiss = vi.fn();
    renderChips({ onAccepted, onDismiss });

    fireEvent.click(
      within(chipWith("Who wrote the first algorithm?")).getByRole("button", {
        name: "Accept",
      }),
    );
    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    fireEvent.click(
      within(chipWith("____ wrote the first algorithm.")).getByRole("button", {
        name: "Accept",
      }),
    );

    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // With every candidate resolved the reader is told the row is finished.
    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
  });
});

describe("CardSuggestions edit (CAP-06)", () => {
  it("persists the edited text, not the suggested text", async () => {
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: () => jsonResponse(201, saved),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderChips({ suggestions: [first] });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "Who published the first algorithm?" },
    });
    fireEvent.change(screen.getByLabelText("Answer"), {
      target: { value: "Ada Lovelace, in 1843" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(init.body as string);
    // The student's words reached the server; the generator's did not.
    expect(body.question).toBe("Who published the first algorithm?");
    expect(body.answer).toBe("Ada Lovelace, in 1843");
    expect(body.question).not.toBe(first.question);
  });
});

describe("CardSuggestions discard (CAP-07)", () => {
  it("drops the candidate without any request at all", async () => {
    // Every route is unregistered, so the routed fetch throws on any call — a
    // discard that posted anything would fail here rather than pass unnoticed.
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    renderChips({ onAccepted });

    fireEvent.click(
      within(chipWith("Who wrote the first algorithm?")).getByRole("button", {
        name: "Discard",
      }),
    );

    await waitFor(() =>
      expect(screen.getAllByTestId("card-suggestion")).toHaveLength(1),
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onAccepted).not.toHaveBeenCalled();
    // The discarded candidate is gone; the other one is untouched.
    expect(screen.queryByText("Who wrote the first algorithm?")).toBeNull();
    expect(screen.getByText("____ wrote the first algorithm.")).toBeTruthy();
  });
});

describe("CardSuggestions failure (CAP-08)", () => {
  it("renders the failure on the chip and accepts a retry", async () => {
    let attempt = 0;
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse(422, { detail: "Card text cannot be empty." })
          : jsonResponse(201, saved);
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    renderChips({ suggestions: [first], onAccepted });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Card text cannot be empty.");
    // The chip survives the failure, so the student can try again in place.
    expect(screen.getByTestId("card-suggestion")).toBeTruthy();
    expect(onAccepted).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith(saved));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps a failure on its own chip, leaving the others acceptable", async () => {
    const fetchMock = routedFetch({
      [`POST ${CARDS_URL}`]: (init) => {
        const body = JSON.parse(init.body as string);
        return body.item_type === "free_recall"
          ? jsonResponse(422, { detail: "Card text cannot be empty." })
          : jsonResponse(201, saved);
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAccepted = vi.fn();
    renderChips({ onAccepted });

    fireEvent.click(
      within(chipWith("Who wrote the first algorithm?")).getByRole("button", {
        name: "Accept",
      }),
    );
    await screen.findByRole("alert");

    // The other candidate is unaffected by its neighbour's failure.
    fireEvent.click(
      within(chipWith("____ wrote the first algorithm.")).getByRole("button", {
        name: "Accept",
      }),
    );
    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith(saved));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });
});

describe("CardSuggestions empty batch (CAP-01)", () => {
  it("reads as no cards for this passage rather than as an error", () => {
    renderChips({ suggestions: [] });

    expect(screen.getByText("No cards for this passage.")).toBeTruthy();
    // Not an error state: nothing is announced as an alert, and there is nothing
    // to accept or retry.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("card-suggestion")).toBeNull();
  });
});
