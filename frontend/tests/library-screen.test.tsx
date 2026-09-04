// @vitest-environment jsdom

/**
 * E3 gate (component) — the library screen's quiz-deck controls on a ready
 * source (QUIZ-20): a first-time source offers "Generate quiz deck"; a source
 * with a deck shows item + due counts, a per-source Review link, and an Anki
 * export link; stale/orphaned items raise a "source changed" badge; a failed job
 * surfaces its error with the generate button as a retry; a failed overview load
 * leaves the reading actions intact with no quiz controls; and generating a deck
 * shows an in-progress state that polls the overview every 3s until the job goes
 * terminal and the finished counts appear.
 *
 * The upload/list/ingestion behaviors of this screen are covered by
 * tests/sources-screen.test.tsx; here the focus is only the quiz additions.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { LibraryScreen } from "../app/components/library-screen";

// jsdom performs no App Router navigation, so `useLinkStatus` is never pending
// on its own; this drives that one export to cover the pending branch (ANSW-10).
const linkStatus = vi.hoisted(() => ({ pending: false }));
vi.mock("next/link", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/link")>();
  return { ...actual, useLinkStatus: () => ({ pending: linkStatus.pending }) };
});

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
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

const readySource = {
  id: "s1",
  title: "Ready Book",
  filename: "s1.epub",
  byte_size: 3,
  content_type: "application/epub+zip",
  status: "ready",
  created_at: "now",
};

function job(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: "job1",
    status,
    attempts: status === "failed" ? 3 : 1,
    generated_count: 0,
    discarded_count: 0,
    failed_sections: 0,
    discard_reasons: {},
    error: null,
    created_at: "now",
    updated_at: "now",
    ...extra,
  };
}

function item(id: string, status: string) {
  return {
    id,
    item_type: "cloze",
    question: "Ada wrote the first ____.",
    status,
    due: "2026-07-16T00:00:00Z",
  };
}

const emptyOverview = {
  items: [],
  counts_by_status: {},
  due_count: 0,
  latest_job: null,
};

const deckOverview = {
  items: [item("i1", "active"), item("i2", "active")],
  counts_by_status: { active: 2 },
  due_count: 2,
  latest_job: job("succeeded", { generated_count: 2 }),
};

const changedOverview = {
  items: [item("i1", "active"), item("i2", "stale"), item("i3", "orphaned")],
  counts_by_status: { active: 1, stale: 1, orphaned: 1 },
  due_count: 1,
  latest_job: job("succeeded", { generated_count: 3 }),
};

const failedOverview = {
  items: [],
  counts_by_status: {},
  due_count: 0,
  latest_job: job("failed", { error: "Generation timed out." }),
};

const QUIZ = "/api/sources/s1/quiz";
const DECK = "/api/sources/s1/quiz/deck";

afterEach(() => {
  cleanup();
  linkStatus.pending = false;
  vi.restoreAllMocks();
});

describe("LibraryScreen pending feedback (ANSW-10)", () => {
  it("gives each entry's reading action a pending indicator while it is navigating", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, deckOverview),
      }),
    );
    linkStatus.pending = true;

    render(<LibraryScreen />);

    for (const name of ["Ask", "Teach", "Read", "Review"]) {
      const link = await screen.findByRole("link", { name });
      expect(within(link).getByTestId("nav-pending")).toBeTruthy();
    }
  });

  it("shows no pending indicator while nothing is navigating", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, deckOverview),
      }),
    );

    render(<LibraryScreen />);

    await screen.findByRole("link", { name: "Read" });
    expect(screen.queryAllByTestId("nav-pending")).toHaveLength(0);
  });
});

describe("LibraryScreen quiz-deck controls (E3)", () => {
  it("offers Generate quiz deck on a ready source with no deck yet", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, emptyOverview),
      }),
    );

    render(<LibraryScreen />);

    expect(
      await screen.findByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
    // No deck yet → no counts, no review/export links.
    expect(screen.queryByTestId("quiz-counts-s1")).toBeNull();
    expect(screen.queryByRole("link", { name: "Review" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Export to Anki" })).toBeNull();
  });

  it("shows item + due counts with Review and Export links once a deck exists", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, deckOverview),
      }),
    );

    render(<LibraryScreen />);

    const counts = await screen.findByTestId("quiz-counts-s1");
    expect(counts.textContent).toContain("2 items");
    expect(counts.textContent).toContain("2 due");
    expect(
      screen.getByRole("link", { name: "Review" }).getAttribute("href"),
    ).toBe("/review?source_id=s1");
    expect(
      screen.getByRole("link", { name: "Export to Anki" }).getAttribute("href"),
    ).toBe("/api/sources/s1/quiz/export");
  });

  it("raises a source-changed badge when items went stale or orphaned", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, changedOverview),
      }),
    );

    render(<LibraryScreen />);

    expect(await screen.findByText("source changed")).toBeTruthy();
  });

  it("hides the source-changed badge when all items are active", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, deckOverview),
      }),
    );

    render(<LibraryScreen />);

    await screen.findByTestId("quiz-counts-s1");
    expect(screen.queryByText("source changed")).toBeNull();
  });

  it("hides the Review link when nothing is due", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () =>
          jsonResponse(200, {
            ...deckOverview,
            due_count: 0,
          }),
      }),
    );

    render(<LibraryScreen />);

    await screen.findByTestId("quiz-counts-s1");
    expect(screen.queryByRole("link", { name: "Review" })).toBeNull();
    // Export stays available for a deck with items even when nothing is due.
    expect(screen.getByRole("link", { name: "Export to Anki" })).toBeTruthy();
  });

  it("surfaces a failed deck job's error with the generate button as retry", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(200, failedOverview),
      }),
    );

    render(<LibraryScreen />);

    const err = await screen.findByTestId("quiz-error-s1");
    expect(err.textContent).toBe("Generation timed out.");
    // The generate button remains as the retry affordance.
    expect(
      screen.getByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
  });

  it("leaves reading actions intact and shows no quiz controls when the overview load fails", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () => jsonResponse(500, { detail: "Boom." }),
      }),
    );

    render(<LibraryScreen />);

    // The reading actions still render for the ready source...
    expect(await screen.findByRole("link", { name: "Ask" })).toBeTruthy();
    // ...but the quiz controls stay hidden on a failed overview load.
    expect(screen.queryByTestId("quiz-s1")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Generate quiz deck" }),
    ).toBeNull();
  });

  it("explains a succeeded empty deck when no section was long enough to quiz (REV-03, REV-07)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () =>
          jsonResponse(200, {
            items: [],
            counts_by_status: {},
            due_count: 0,
            latest_job: job("succeeded", {
              generated_count: 0,
              discarded_count: 0,
              failed_sections: 0,
            }),
          }),
      }),
    );

    render(<LibraryScreen />);

    const honesty = await screen.findByTestId("quiz-honesty-s1");
    expect(honesty.textContent).toMatch(/no section long enough/i);
    expect(honesty.textContent).toMatch(/200\+/);
    expect(honesty.textContent).toMatch(/leaf/i);
    expect(
      screen.getByRole("link", { name: /highlight a passage/i }),
    ).toBeTruthy();
    expect(screen.queryByTestId("quiz-error-s1")).toBeNull();
    expect(screen.queryByTestId("quiz-counts-s1")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
  });

  it("explains when drafts were written but none survived quality checks (REV-04)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () =>
          jsonResponse(200, {
            items: [],
            counts_by_status: {},
            due_count: 0,
            latest_job: job("succeeded", {
              generated_count: 0,
              discarded_count: 7,
              failed_sections: 0,
              discard_reasons: { generic_stem: 7 },
            }),
          }),
      }),
    );

    render(<LibraryScreen />);

    const honesty = await screen.findByTestId("quiz-honesty-s1");
    expect(honesty.textContent).toMatch(/drafts were written/i);
    expect(honesty.textContent).toMatch(/none survived/i);
    expect(honesty.textContent).toContain("7");
    expect(screen.queryByTestId("quiz-error-s1")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
  });

  it("shows item and due counts with a quiet discarded footnote (REV-05)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () =>
          jsonResponse(200, {
            items: [item("i1", "active"), item("i2", "active")],
            counts_by_status: { active: 2 },
            due_count: 1,
            latest_job: job("succeeded", {
              generated_count: 2,
              discarded_count: 4,
              failed_sections: 0,
              discard_reasons: { yes_no: 4 },
            }),
          }),
      }),
    );

    render(<LibraryScreen />);

    const counts = await screen.findByTestId("quiz-counts-s1");
    expect(counts.textContent).toContain("2 items");
    expect(counts.textContent).toContain("1 due");
    const footnote = screen.getByTestId("quiz-discard-footnote-s1");
    expect(footnote.textContent).toContain("4");
    expect(footnote.className).toMatch(/muted/);
    expect(screen.queryByTestId("quiz-honesty-s1")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
  });

  it("mentions the saved count and failed-section count when some sections fail (REV-06)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [readySource]),
        [`GET ${QUIZ}`]: () =>
          jsonResponse(200, {
            items: [item("i1", "active")],
            counts_by_status: { active: 1 },
            due_count: 1,
            latest_job: job("succeeded", {
              generated_count: 1,
              discarded_count: 0,
              failed_sections: 3,
            }),
          }),
      }),
    );

    render(<LibraryScreen />);

    const partial = await screen.findByTestId("quiz-partial-s1");
    expect(partial.textContent).toMatch(/1/);
    expect(partial.textContent).toMatch(/saved/i);
    expect(partial.textContent).toMatch(/3/);
    expect(partial.textContent).toMatch(/section/i);
    expect(screen.getByTestId("quiz-counts-s1").textContent).toContain("1 item");
    expect(
      screen.getByRole("button", { name: "Generate quiz deck" }),
    ).toBeTruthy();
  });

  it("generates a deck and shows the in-progress state while the job is queued", async () => {
    // The queued-job → overview poll → finished-counts transition is covered by
    // tests/use-quiz-deck-polling.test.tsx (the deck-polling hook) and the
    // counts-once-a-deck-exists case above; here we assert the generate action
    // itself POSTs the deck and flips the control to its disabled progress state.
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [readySource]),
      [`GET ${QUIZ}`]: () => jsonResponse(200, emptyOverview),
      [`POST ${DECK}`]: () => jsonResponse(202, job("queued")),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);

    const generate = await screen.findByRole("button", {
      name: "Generate quiz deck",
    });
    fireEvent.click(generate);

    // The queued job flips the control to a disabled in-progress state.
    const progress = (await screen.findByRole("button", {
      name: /Generating deck/,
    })) as HTMLButtonElement;
    expect(progress.disabled).toBe(true);

    // The generate action POSTed to the deck endpoint.
    const deckPost = fetchMock.mock.calls.find(
      ([url, init]) => url === DECK && (init as RequestInit)?.method === "POST",
    );
    expect(deckPost).toBeDefined();
  });
});

describe("LibraryScreen quiz controls scope (E3)", () => {
  it("does not render quiz controls for a non-ready source", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () =>
          jsonResponse(200, [{ ...readySource, status: "uploaded" }]),
      }),
    );

    render(<LibraryScreen />);

    await screen.findByText("Ready Book");
    expect(screen.queryByTestId("quiz-s1")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Generate quiz deck" }),
    ).toBeNull();
  });
});
