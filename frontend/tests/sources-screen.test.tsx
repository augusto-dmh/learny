// @vitest-environment jsdom

/**
 * C gate (component) — the library screen lists sources as cards through the
 * same-origin proxy, uploads an EPUB (add-on-success), surfaces upload/validation
 * errors without adding a row, links ready books to Ask/Teach/Read, offers a
 * (re)start-ingestion control for uploaded/failed sources, shows a failed
 * source's latest ingestion event message, and does a UX-only redirect when
 * unauthenticated (FE-20/FE-21; SRC-11 behaviors preserved). The section-tree
 * browsing that SourcesPanel embedded now lives in the sidebar
 * (tests/app-sidebar.test.tsx).
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

import { LibraryScreen } from "../app/components/library-screen";

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

function sourceRow(id: string, title: string, status: string) {
  return {
    id,
    title,
    filename: `${id}.epub`,
    byte_size: 3,
    content_type: "application/epub+zip",
    status,
    created_at: "now",
  };
}

/** One source in each of the four projection states. */
const mixed = [
  sourceRow("s-up", "Uploaded Book", "uploaded"),
  sourceRow("s-proc", "Processing Book", "processing"),
  sourceRow("s-ready", "Ready Book", "ready"),
  sourceRow("s-fail", "Failed Book", "failed"),
];

/** The queued job the backend returns from POST .../ingestion. */
const ingestionQueued = {
  id: "j1",
  status: "queued",
  attempts: 0,
  error: null,
  created_at: "now",
  updated_at: "now",
  events: [{ type: "queued", message: null, created_at: "now" }],
};

/** The failed job the library reads to show a failed source's latest message. */
const failedIngestion = {
  id: "j-fail",
  status: "failed",
  attempts: 1,
  error: "Ingestion failed.",
  created_at: "now",
  updated_at: "now",
  events: [
    { type: "queued", message: null, created_at: "t0" },
    { type: "failed", message: "EPUB is missing its spine.", created_at: "t1" },
  ],
};

/** A still-running job for the processing source's 3s poll (FE-19). */
const runningIngestion = {
  id: "j-proc",
  status: "running",
  attempts: 1,
  error: null,
  created_at: "now",
  updated_at: "now",
  events: [{ type: "running", message: null, created_at: "t0" }],
};

/** Handler map for a `mixed` render: sources list plus the ingestion reads. */
function mixedHandlers(extra: Record<string, Handler> = {}) {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    "GET /api/sources": () => jsonResponse(200, mixed),
    "GET /api/sources/s-fail/ingestion": () => jsonResponse(200, failedIngestion),
    "GET /api/sources/s-proc/ingestion": () => jsonResponse(200, runningIngestion),
    ...extra,
  };
}

function selectFileAndTitle(title: string) {
  const file = new File([new Uint8Array([1, 2, 3])], "book.epub", {
    type: "application/epub+zip",
  });
  const fileInput = screen.getByLabelText("EPUB file") as HTMLInputElement;
  // jsdom won't let fireEvent assign an input's FileList; define it directly so
  // the file field is satisfied and the form actually submits.
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

describe("LibraryScreen (upload + list)", () => {
  it("renders the empty-state when the user has no sources", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, []),
      }),
    );

    render(<LibraryScreen />);

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

    render(<LibraryScreen />);
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

    render(<LibraryScreen />);
    await screen.findByText("No sources yet.");

    selectFileAndTitle("Not a book");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Only EPUB files are supported.");
    expect(screen.queryByText("Not a book")).toBeNull();
    expect(screen.getByText("No sources yet.")).toBeTruthy();
  });

  it("shows a readable validation error and posts nothing when no file is chosen", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, []),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("No sources yet.");

    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Titled but fileless" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Choose an EPUB file to upload.");
    // No upload POST was issued.
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      false,
    );
  });

  it("fires the UX-only redirect callback when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => new Response(null, { status: 401 }),
      }),
    );

    const onRequireAuth = vi.fn();
    render(<LibraryScreen onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });

  it("shows each source's ingestion status badge per card", async () => {
    vi.stubGlobal("fetch", routedFetch(mixedHandlers()));

    render(<LibraryScreen />);
    await screen.findByText("Uploaded Book");

    expect(screen.getByTestId("status-s-up").textContent).toBe("uploaded");
    expect(screen.getByTestId("status-s-proc").textContent).toBe("processing");
    expect(screen.getByTestId("status-s-ready").textContent).toBe("ready");
    expect(screen.getByTestId("status-s-fail").textContent).toBe("failed");
  });

  it("links only ready cards to their Ask, Teach, and Read views", async () => {
    vi.stubGlobal("fetch", routedFetch(mixedHandlers()));

    render(<LibraryScreen />);
    await screen.findByText("Ready Book");

    // Exactly one of each action link — all on the sole ready card.
    for (const name of ["Ask", "Teach", "Read"]) {
      const links = screen.getAllByRole("link", { name });
      expect(links).toHaveLength(1);
    }
    const readyLi = screen.getByTestId("status-s-ready").closest("li");
    expect(
      within(readyLi!).getByRole("link", { name: "Ask" }).getAttribute("href"),
    ).toBe("/sources/s-ready/ask");
    expect(
      within(readyLi!).getByRole("link", { name: "Teach" }).getAttribute("href"),
    ).toBe("/sources/s-ready/teach");
    expect(
      within(readyLi!).getByRole("link", { name: "Read" }).getAttribute("href"),
    ).toBe("/sources/s-ready/read");

    // Non-ready cards offer no action links.
    for (const id of ["s-up", "s-proc", "s-fail"]) {
      const li = screen.getByTestId(`status-${id}`).closest("li");
      expect(within(li!).queryByRole("link")).toBeNull();
    }
  });
});

describe("LibraryScreen (ingestion start)", () => {
  it("offers Start ingestion only for uploaded sources", async () => {
    vi.stubGlobal("fetch", routedFetch(mixedHandlers()));

    render(<LibraryScreen />);
    await screen.findByText("Uploaded Book");

    // Exactly one Start control — on the sole uploaded card.
    const startButtons = screen.getAllByRole("button", {
      name: "Start ingestion",
    });
    expect(startButtons).toHaveLength(1);
    const uploadedLi = screen.getByTestId("status-s-up").closest("li");
    expect(
      within(uploadedLi!).getByRole("button", { name: "Start ingestion" }),
    ).toBeTruthy();

    // The processing card offers no controls; the ready card offers only the
    // (confirm-gated) re-ingest control, never a start control.
    const procLi = screen.getByTestId("status-s-proc").closest("li");
    expect(within(procLi!).queryByRole("button")).toBeNull();
    const readyLi = screen.getByTestId("status-s-ready").closest("li");
    const readyButtons = within(readyLi!).getAllByRole("button");
    expect(readyButtons.map((b) => b.textContent)).toEqual(["Re-ingest"]);
  });

  it("starts ingestion through the proxy and reflects processing on success", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[0]]),
      "POST /api/sources/s-up/ingestion": () =>
        jsonResponse(202, ingestionQueued),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    await waitFor(() =>
      expect(screen.getByTestId("status-s-up").textContent).toBe("processing"),
    );
    expect(
      screen.queryByRole("button", { name: "Start ingestion" }),
    ).toBeNull();

    const posted = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(posted?.[0]).toBe("/api/sources/s-up/ingestion");
  });

  it("shows Starting… + disables the button in flight and blocks a double-start", async () => {
    let resolvePost!: (r: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolvePost = resolve;
    });
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[0]]),
      "POST /api/sources/s-up/ingestion": () => pending,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    const starting = (await screen.findByRole("button", {
      name: "Starting…",
    })) as HTMLButtonElement;
    expect(starting.disabled).toBe(true);

    fireEvent.click(starting);
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);

    resolvePost(jsonResponse(202, ingestionQueued));
    await waitFor(() =>
      expect(screen.getByTestId("status-s-up").textContent).toBe("processing"),
    );
  });

  it("surfaces the error and keeps the card uploaded when the start is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[0]]),
        "POST /api/sources/s-up/ingestion": () =>
          jsonResponse(409, { detail: "Ingestion is already in progress." }),
      }),
    );

    render(<LibraryScreen />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Ingestion is already in progress.");
    expect(screen.getByTestId("status-s-up").textContent).toBe("uploaded");
    expect(
      screen.getByRole("button", { name: "Start ingestion" }),
    ).toBeTruthy();
  });
});

describe("LibraryScreen (failed source)", () => {
  it("shows the failed source's latest event message with a restart control", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[3]]),
        "GET /api/sources/s-fail/ingestion": () =>
          jsonResponse(200, failedIngestion),
      }),
    );

    render(<LibraryScreen />);
    await screen.findByText("Failed Book");

    // The latest ingestion event message is surfaced...
    const message = await screen.findByTestId("failure-s-fail");
    expect(message.textContent).toBe("EPUB is missing its spine.");
    // ...alongside the restart control (still a start-ingestion POST).
    expect(
      screen.getByRole("button", { name: "Restart ingestion" }),
    ).toBeTruthy();
  });

  it("restarts a failed source through the proxy and reflects processing", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[3]]),
      "GET /api/sources/s-fail/ingestion": () =>
        jsonResponse(200, failedIngestion),
      "POST /api/sources/s-fail/ingestion": () =>
        jsonResponse(202, ingestionQueued),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByTestId("failure-s-fail");

    fireEvent.click(screen.getByRole("button", { name: "Restart ingestion" }));

    await waitFor(() =>
      expect(screen.getByTestId("status-s-fail").textContent).toBe("processing"),
    );
    const posted = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(posted?.[0]).toBe("/api/sources/s-fail/ingestion");
  });
});

describe("LibraryScreen (re-ingest ready source)", () => {
  it("asks for confirmation before posting anything", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));

    // The confirmation replaces the trigger: warning text plus confirm/cancel.
    expect(screen.queryByRole("button", { name: "Re-ingest" })).toBeNull();
    expect(
      screen.getByText(/rebuilds this book.s corpus/i),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Confirm re-ingest" }),
    ).toBeTruthy();
    // Nothing has been posted yet.
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(0);
  });

  it("re-ingests through the proxy after confirmation and reflects processing", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
      "POST /api/sources/s-ready/ingestion": () =>
        jsonResponse(202, ingestionQueued),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm re-ingest" }));

    await waitFor(() =>
      expect(screen.getByTestId("status-s-ready").textContent).toBe(
        "processing",
      ),
    );
    const posted = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(posted?.[0]).toBe("/api/sources/s-ready/ingestion");
  });

  it("cancel dismisses the confirmation without posting", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryScreen />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "Re-ingest" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // Back to the collapsed trigger; the card is untouched and nothing posted.
    expect(screen.getByRole("button", { name: "Re-ingest" })).toBeTruthy();
    expect(screen.getByTestId("status-s-ready").textContent).toBe("ready");
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(0);
  });
});
