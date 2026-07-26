// @vitest-environment jsdom

/**
 * Managing conversations from the dock, against the real panels rather than
 * stubs — renaming a thread, deleting one, and the case that matters most:
 * deleting the thread the panel is currently showing. A conversation the server
 * no longer has must not stay on screen, so the panel it was open in returns to
 * its empty state instead of rendering a thread that is gone.
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

import { ReaderPanel } from "../app/components/reader-panel";
import {
  readActiveConversation,
  writeActiveConversation,
} from "../app/lib/active-conversation";

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

// The dock asks for one bounded page, so the window is part of the URL.
const LIST_URL = "/api/conversations?source_id=s1&limit=20&offset=0";
const CONVERSATION_URL = "/api/conversations/conv1";

const summary = {
  id: "conv1",
  source_id: "s1",
  source_title: "A Book",
  title: "Ada Lovelace",
  scope_anchors: [],
  include_notes: true,
  turn_count: 1,
  created_at: "now",
  updated_at: "now",
};

const detail = {
  id: "conv1",
  source_id: "s1",
  title: "Ada Lovelace",
  scope_anchors: [],
  include_notes: true,
  created_at: "now",
  updated_at: "now",
  turns: [
    {
      turn_index: 0,
      message: "Who wrote the first algorithm?",
      mode: "answer",
      answer_status: "answered",
      text: "Ada Lovelace did.",
      citations: [],
      evidence_count: 4,
      model: "local-extractive",
      created_at: "now",
    },
  ],
};

function renderDock(handlers: Record<string, Handler>) {
  const fetchMock = routedFetch(handlers);
  vi.stubGlobal("fetch", fetchMock);
  render(
    <ReaderPanel
      sourceId="s1"
      csrf="csrf-xyz"
      mode="ask"
      onModeChange={() => {}}
      onClose={() => {}}
    />,
  );
  return fetchMock;
}

function callsTo(
  fetchMock: ReturnType<typeof routedFetch>,
  url: string,
): unknown[][] {
  return fetchMock.mock.calls.filter(([called]) => called === url);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("renaming a conversation from the dock", () => {
  it("persists the new title and shows it in the list without a reload", async () => {
    const fetchMock = renderDock({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, [summary]),
      [`PATCH ${CONVERSATION_URL}`]: () =>
        jsonResponse(200, { ...summary, title: "Algorithms" }),
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "Rename Ada Lovelace" }),
    );
    fireEvent.change(screen.getByLabelText("New title"), {
      target: { value: "Algorithms" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save title" }));
    });

    // The new title is stored and the row shows it — the list was never refetched.
    expect(callsTo(fetchMock, CONVERSATION_URL)).toHaveLength(1);
    expect(
      JSON.parse(
        (callsTo(fetchMock, CONVERSATION_URL)[0][1] as RequestInit).body as string,
      ),
    ).toEqual({ title: "Algorithms" });
    expect(
      await screen.findByRole("button", { name: "Resume Algorithms" }),
    ).toBeTruthy();
    expect(callsTo(fetchMock, LIST_URL)).toHaveLength(1);
  });

  it("leaves the stored title unchanged when the new one is blank", async () => {
    const fetchMock = renderDock({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, [summary]),
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "Rename Ada Lovelace" }),
    );
    fireEvent.change(screen.getByLabelText("New title"), {
      target: { value: "   " },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save title" }));
    });

    // Nothing was sent, so nothing changed.
    expect(callsTo(fetchMock, CONVERSATION_URL)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Cancel rename" }));
    expect(
      screen.getByRole("button", { name: "Resume Ada Lovelace" }),
    ).toBeTruthy();
  });

  it("keeps the old title and explains itself when the server rejects the new one", async () => {
    renderDock({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, [summary]),
      [`PATCH ${CONVERSATION_URL}`]: () =>
        jsonResponse(422, { detail: [{ msg: "too long" }] }),
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "Rename Ada Lovelace" }),
    );
    fireEvent.change(screen.getByLabelText("New title"), {
      target: { value: "x".repeat(500) },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save title" }));
    });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Could not rename");
    fireEvent.click(screen.getByRole("button", { name: "Cancel rename" }));
    expect(
      screen.getByRole("button", { name: "Resume Ada Lovelace" }),
    ).toBeTruthy();
  });
});

describe("deleting a conversation from the dock", () => {
  it("removes it from the list", async () => {
    const fetchMock = renderDock({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, [summary]),
      [`DELETE ${CONVERSATION_URL}`]: () => new Response(null, { status: 204 }),
    });

    const deleteButton = await screen.findByRole("button", {
      name: "Delete Ada Lovelace",
    });
    await act(async () => {
      fireEvent.click(deleteButton);
    });

    expect(callsTo(fetchMock, CONVERSATION_URL)).toHaveLength(1);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Resume Ada Lovelace" })).toBeNull(),
    );
    expect(screen.getByText("No conversations yet.")).toBeTruthy();
  });

  it("returns the panel to its empty state when the open conversation is deleted", async () => {
    writeActiveConversation("s1", "ask", "conv1");
    renderDock({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, [summary]),
      [`GET ${CONVERSATION_URL}`]: () => jsonResponse(200, detail),
      [`DELETE ${CONVERSATION_URL}`]: () => new Response(null, { status: 204 }),
    });

    // The panel is showing that conversation's stored turn.
    expect(await screen.findByText("Ada Lovelace did.")).toBeTruthy();

    const deleteButton = await screen.findByRole("button", {
      name: "Delete Ada Lovelace",
    });
    await act(async () => {
      fireEvent.click(deleteButton);
    });

    // No part of the deleted thread is left rendered, and the panel is back to
    // the state it has before a reader asks anything.
    await waitFor(() =>
      expect(screen.queryByText("Ada Lovelace did.")).toBeNull(),
    );
    expect(screen.queryByText("Who wrote the first algorithm?")).toBeNull();
    expect(screen.getByLabelText("suggested prompts")).toBeTruthy();
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });
});
