// @vitest-environment jsdom

/**
 * NF-13/14 gate (component) — the notes list screen. It lists the caller's notes
 * as title-linked cards with tag chips and a badge per distinct anchor status
 * (an orphaned anchor rendered distinctly and never hidden), filters the list to
 * a tag when its chip is clicked (re-fetched server-side) and clears the filter,
 * creates a note from the form and opens it, and settles nothing-yet and
 * signed-out to their own readable states.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { NotesScreen } from "../app/components/notes/notes-screen";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
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

afterEach(() => {
  cleanup();
  nav.push.mockClear();
  vi.restoreAllMocks();
});

describe("NotesScreen (NF-13/14)", () => {
  it("lists notes with title links, tag chips, and anchor-status badges", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
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

  it("creates a note from the form and opens it", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/notes": () => jsonResponse(200, []),
        "POST /api/notes": () =>
          jsonResponse(201, {
            id: "n9",
            title: "Fresh note",
            body_markdown: "",
            tags: [],
            anchors: [],
            created_at: "now",
            updated_at: "now",
          }),
      }),
    );

    render(<NotesScreen />);

    const input = await screen.findByLabelText("Title");
    fireEvent.change(input, { target: { value: "Fresh note" } });
    fireEvent.click(screen.getByRole("button", { name: "Create note" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes/n9"));
  });

  it("offers an Export vault download pointing at the export endpoint (NL-16)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
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
        "GET /api/notes": () => jsonResponse(200, []),
      }),
    );

    render(<NotesScreen />);

    expect(await screen.findByText("No notes yet.")).toBeTruthy();
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
