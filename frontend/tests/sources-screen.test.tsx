// @vitest-environment jsdom

/**
 * T8 gate (component) — the /sources screen lists sources through the same-origin
 * proxy, uploads an EPUB (add-on-success), surfaces API rejections without
 * adding a row, and does a UX-only redirect when unauthenticated (SRC-11).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourcesPanel } from "../app/components/SourcesPanel";

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

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

const created = {
  id: "s1",
  title: "My Book",
  filename: "book.epub",
  byte_size: 3,
  content_type: "application/epub+zip",
  status: "uploaded",
  created_at: "now",
};

function selectFileAndTitle(title: string) {
  const file = new File([new Uint8Array([1, 2, 3])], "book.epub", {
    type: "application/epub+zip",
  });
  const fileInput = screen.getByLabelText("EPUB file") as HTMLInputElement;
  // jsdom won't let fireEvent assign an input's FileList; define it directly so
  // the `required` file field is satisfied and the form actually submits.
  Object.defineProperty(fileInput, "files", {
    value: [file],
    configurable: true,
  });
  fireEvent.change(fileInput);
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: title } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SourcesPanel (T8)", () => {
  it("renders the empty-state when the user has no sources", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, []),
      }),
    );

    render(<SourcesPanel />);

    expect(await screen.findByText("No sources yet.")).toBeTruthy();
  });

  it("adds the source to the list on a successful upload", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, []),
        "POST /api/sources": () => jsonResponse(201, created),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("No sources yet.");

    selectFileAndTitle("My Book");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    expect(await screen.findByText("My Book")).toBeTruthy();
    expect(screen.queryByText("No sources yet.")).toBeNull();
  });

  it("surfaces the error and adds nothing when the API rejects the upload", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, []),
        "POST /api/sources": () =>
          jsonResponse(415, { detail: "Only EPUB files are supported." }),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("No sources yet.");

    selectFileAndTitle("Not a book");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Only EPUB files are supported.");
    expect(screen.queryByText("Not a book")).toBeNull();
    expect(screen.getByText("No sources yet.")).toBeTruthy();
  });

  it("fires the UX-only redirect callback when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<SourcesPanel onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});
