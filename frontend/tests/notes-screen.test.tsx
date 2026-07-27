// @vitest-environment jsdom

/**
 * NF-13/14 gate (component) — the notes list screen. It lists the caller's notes
 * as title-linked cards with tag chips and a badge per distinct anchor status
 * (an orphaned anchor rendered distinctly and never hidden), filters the list to
 * a tag when its chip is clicked (re-fetched server-side) and clears the filter,
 * and settles nothing-yet and signed-out to their own readable states. It offers
 * no way to mint a note: every note is born from a passage, so the title-only
 * form is gone (P3 AC 5).
 *
 * It is also the cross-book surface (P4): unfiltered it holds every book's notes,
 * a book picker narrows it to one, and picking every book again restores the
 * cross-book list. A book the caller does not own answers 404, which must read as
 * a message rather than a broken screen.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { NotesScreen } from "../app/components/notes/notes-screen";

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

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

function summary(id: string, title: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    title,
    tags: [],
    anchor_statuses: [],
    created_at: "now",
    updated_at: "now",
    ...extra,
  };
}

const notes = [
  summary("n1", "Ada's algorithm", {
    tags: ["history"],
    anchor_statuses: ["active", "orphaned"],
  }),
  summary("n2", "Babbage engine", { tags: ["history", "machines"] }),
];

/** The caller's books, which the picker offers — "Ada's algorithm" is s1's. */
function source(id: string, title: string) {
  return {
    id,
    title,
    filename: `${id}.epub`,
    byte_size: 1024,
    content_type: "application/epub+zip",
    status: "ready",
    created_at: "now",
  };
}

const sources = [source("s1", "Notes on the Engine"), source("s2", "Memoirs")];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("NotesScreen (NF-13/14)", () => {
  it("lists notes with title links, tag chips, and anchor-status badges", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
      }),
    );

    render(<NotesScreen />);

    // Titles link to their detail routes.
    const title = await screen.findByRole("link", { name: "Ada's algorithm" });
    expect(title.getAttribute("href")).toBe("/notes/n1");
    // Tag chips render.
    expect(screen.getAllByText("history").length).toBeGreaterThan(0);
    // The orphaned anchor gets its distinct badge and is never hidden.
    expect(screen.getByTestId("anchor-status-orphaned")).toBeTruthy();
    expect(screen.getByTestId("anchor-status-active")).toBeTruthy();
  });

  it("filters the list to a tag when its chip is clicked and clears the filter", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
        "GET /api/notes?tag=history": () =>
          jsonResponse(200, [notes[0]]),
      }),
    );

    render(<NotesScreen />);

    // Filter by a "history" chip (both notes carry it; either drives the filter).
    const chips = await screen.findAllByRole("button", {
      name: "Filter by history",
    });
    fireEvent.click(chips[0]);

    // The filtered list re-fetched and the other note dropped out.
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Babbage engine" })).toBeNull(),
    );
    expect(screen.getByText("Filtered by")).toBeTruthy();

    // Clearing the filter restores the full list.
    fireEvent.click(screen.getByRole("button", { name: "Clear filter" }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Babbage engine" })).toBeTruthy(),
    );
  });

  it("offers no title-only creation control (P3 AC 5)", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, sources),
      "GET /api/notes": () => jsonResponse(200, notes),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NotesScreen />);

    // Wait for the loaded screen, then look for any way to mint a note here.
    await screen.findByRole("link", { name: "Ada's algorithm" });
    expect(screen.queryByRole("form", { name: "create note" })).toBeNull();
    expect(screen.queryByLabelText("Title")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create note" })).toBeNull();
    expect(screen.queryByText("New note")).toBeNull();
    // And nothing the screen did posted a note.
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toEqual([]);
  });

  it("offers an Export vault download pointing at the export endpoint (NL-16)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, []),
      }),
    );

    render(<NotesScreen />);

    const link = await screen.findByRole("link", { name: "Export vault" });
    expect(link.getAttribute("href")).toBe("/api/export/vault");
    expect(link.hasAttribute("download")).toBe(true);
  });

  it("shows a nothing-yet state when the user has no notes", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, []),
      }),
    );

    render(<NotesScreen />);

    expect(
      await screen.findByText(
        "No notes yet. Open a book and select a passage to start one.",
      ),
    ).toBeTruthy();
  });

  it("still lists the notes when the library cannot be loaded", async () => {
    // The picker is a convenience over the list, not a precondition for it: if the
    // library read fails there is simply nothing to narrow by, and the notes — the
    // thing the screen exists for — must still arrive.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(500, { detail: "boom" }),
        "GET /api/notes": () => jsonResponse(200, notes),
      }),
    );

    render(<NotesScreen />);

    expect(await screen.findByRole("link", { name: "Ada's algorithm" })).toBeTruthy();
    // The same locator the narrowing test uses to drive the picker, so this asserts
    // its absence rather than the absence of something that was never there.
    expect(screen.queryByLabelText("Book")).toBeNull();
  });

  it("lists notes across every book when no book is picked (P4 AC 1)", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, sources),
      "GET /api/notes": () => jsonResponse(200, notes),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<NotesScreen />);

    // Both books' notes are present, and the request carried no book scope.
    expect(await screen.findByRole("link", { name: "Ada's algorithm" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Babbage engine" })).toBeTruthy();
    const notesCalls = fetchMock.mock.calls
      .map(([url]) => url)
      .filter((url) => url.startsWith("/api/notes"));
    expect(notesCalls).toEqual(["/api/notes"]);
  });

  it("narrows the list to one book and restores it when cleared (P4 AC 2, 3)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
        "GET /api/notes?source_id=s1": () => jsonResponse(200, [notes[0]]),
      }),
    );

    render(<NotesScreen />);

    const picker = await screen.findByLabelText("Book");
    fireEvent.change(picker, { target: { value: "s1" } });

    // Only the picked book's notes remain.
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Babbage engine" })).toBeNull(),
    );
    expect(screen.getByRole("link", { name: "Ada's algorithm" })).toBeTruthy();

    // Picking every book again restores the cross-book list.
    fireEvent.change(picker, { target: { value: "" } });
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Babbage engine" })).toBeTruthy(),
    );
  });

  it("offers every book the caller owns in the picker", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
      }),
    );

    render(<NotesScreen />);

    expect(await screen.findByRole("option", { name: "All books" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Notes on the Engine" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Memoirs" })).toBeTruthy();
  });

  it("reads a book the caller does not own as a message, not a crash (P4 AC 4)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
        "GET /api/notes?source_id=s2": () =>
          jsonResponse(404, { detail: "Source not found." }),
      }),
    );

    render(<NotesScreen />);

    const picker = await screen.findByLabelText("Book");
    fireEvent.change(picker, { target: { value: "s2" } });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Source not found.");
  });

  it("says a picked book has nothing yet rather than nothing at all", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, sources),
        "GET /api/notes": () => jsonResponse(200, notes),
        "GET /api/notes?source_id=s2": () => jsonResponse(200, []),
      }),
    );

    render(<NotesScreen />);

    fireEvent.change(await screen.findByLabelText("Book"), {
      target: { value: "s2" },
    });

    expect(await screen.findByText("No notes from this book yet.")).toBeTruthy();
  });

  it("redirects and shows a signed-out state when unauthenticated", async () => {
    const onRequireAuth = vi.fn();
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    render(<NotesScreen onRequireAuth={onRequireAuth} />);

    expect(await screen.findByText("You are signed out.")).toBeTruthy();
    expect(onRequireAuth).toHaveBeenCalled();
  });
});
