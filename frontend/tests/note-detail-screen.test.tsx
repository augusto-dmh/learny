// @vitest-environment jsdom

/**
 * NF-13/14 gate (component) — the note detail screen. It loads a note and its
 * backlinks, edits the body in a textarea with a preview toggle, enables Save only
 * while dirty and persists the edit (re-baselining afterward), lists anchored
 * passages with a jump-back link for a live anchor and a distinct badge + quote
 * snapshot for an orphaned one (NF-14), links each backlink to its note, flags an
 * over-cap save, and deletes behind a confirm before returning to the list.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { NoteDetailScreen } from "../app/components/notes/note-detail-screen";

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

const liveAnchor = {
  id: "a1",
  source_id: "s1",
  source_title: "Ready Book",
  anchor: "chapter-1.xhtml#core-idea",
  section_path: ["Chapter 1", "Core Idea"],
  block_ordinal: 0,
  start_offset: 0,
  end_offset: 5,
  quote_exact: "Ada wrote the first algorithm",
  quote_prefix: "",
  quote_suffix: "",
  status: "active",
};

const orphanAnchor = {
  ...liveAnchor,
  id: "a2",
  quote_exact: "A passage that vanished on re-ingest",
  status: "orphaned",
};

const note = {
  id: "n1",
  title: "Ada's algorithm",
  body_markdown: "A note about [[Babbage]].",
  tags: ["history"],
  anchors: [liveAnchor, orphanAnchor],
  created_at: "now",
  updated_at: "now",
};

const backlinks = [{ note_id: "n2", title: "Babbage engine" }];

const NOTE_URL = "/api/notes/n1";
const BACKLINKS_URL = "/api/notes/n1/backlinks";

function loadHandlers(extra: Record<string, Handler> = {}) {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    [`GET ${NOTE_URL}`]: () => jsonResponse(200, note),
    [`GET ${BACKLINKS_URL}`]: () => jsonResponse(200, backlinks),
    ...extra,
  };
}

afterEach(() => {
  cleanup();
  nav.push.mockClear();
  vi.restoreAllMocks();
});

describe("NoteDetailScreen (NF-13/14)", () => {
  it("loads the note, its anchored passages, and its backlinks", async () => {
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));

    render(<NoteDetailScreen noteId="n1" />);

    // Title and body hydrate the editor.
    expect(
      ((await screen.findByLabelText("Title")) as HTMLInputElement).value,
    ).toBe("Ada's algorithm");
    expect((screen.getByLabelText("Body") as HTMLTextAreaElement).value).toBe(
      "A note about [[Babbage]].",
    );

    // A live anchor offers a jump-back into the reader at its encoded anchor.
    const jump = screen.getByRole("link", { name: "Jump to passage" });
    expect(jump.getAttribute("href")).toBe(
      "/sources/s1/read?anchor=chapter-1.xhtml%23core-idea",
    );

    // The orphaned anchor keeps its quote and a distinct badge, and offers no jump.
    expect(screen.getByText("A passage that vanished on re-ingest")).toBeTruthy();
    expect(screen.getByTestId("anchor-status-orphaned")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Jump to passage" }).length).toBe(1);

    // A backlink links to its note.
    expect(
      screen.getByRole("link", { name: "Babbage engine" }).getAttribute("href"),
    ).toBe("/notes/n2");
  });

  it("enables Save only while dirty and persists the edit", async () => {
    let patchBody: unknown = null;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`PATCH ${NOTE_URL}`]: (init) => {
            patchBody = JSON.parse(init.body as string);
            return jsonResponse(200, { ...note, body_markdown: "Edited body." });
          },
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    const save = (await screen.findByRole("button", {
      name: "Save",
    })) as HTMLButtonElement;
    // Nothing changed yet → Save is disabled.
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Body"), {
      target: { value: "Edited body." },
    });
    expect(save.disabled).toBe(false);

    fireEvent.click(save);

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({
      title: "Ada's algorithm",
      body_markdown: "Edited body.",
      tags: ["history"],
    });
    // Re-baselined after the save → Save disabled again.
    await waitFor(() => expect(save.disabled).toBe(true));
  });

  it("toggles a Markdown preview of the body", async () => {
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview" }));

    const preview = await screen.findByTestId("note-preview");
    expect(preview.textContent).toContain("A note about");
    // The textarea is swapped out while previewing.
    expect(screen.queryByLabelText("Body")).toBeNull();
  });

  it("flags an over-cap save without persisting a broken state", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`PATCH ${NOTE_URL}`]: () =>
            jsonResponse(422, { detail: "Note body is too long." }),
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.change(await screen.findByLabelText("Body"), {
      target: { value: "way too long" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too long to save/i);
  });

  it("deletes the note behind a confirm and returns to the list", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`DELETE ${NOTE_URL}`]: () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    // The destructive action is confirm-gated.
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes"));
  });
});
