// @vitest-environment jsdom

/**
 * T8 gate (component) — the /sources screen lists sources through the same-origin
 * proxy, uploads an EPUB (add-on-success), surfaces API rejections without
 * adding a row, and does a UX-only redirect when unauthenticated (SRC-11).
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

/** The parsed structure the backend returns for the ready fixture source. */
const readyStructure = {
  title: "Ready Book",
  authors: ["Ada Lovelace"],
  language: "en",
  sections: [
    {
      title: "Chapter 1",
      depth: 0,
      section_path: ["Chapter 1"],
      anchor: "c1.xhtml",
      children: [
        {
          title: "Section 1.1",
          depth: 1,
          section_path: ["Chapter 1", "Section 1.1"],
          anchor: "c1.xhtml#s1",
          children: [],
        },
      ],
    },
    {
      title: "Chapter 2",
      depth: 0,
      section_path: ["Chapter 2"],
      anchor: "c2.xhtml",
      children: [],
    },
  ],
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

  it("shows each source's ingestion status badge per row", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, mixed),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Uploaded Book");

    expect(screen.getByTestId("status-s-up").textContent).toBe("uploaded");
    expect(screen.getByTestId("status-s-proc").textContent).toBe("processing");
    expect(screen.getByTestId("status-s-ready").textContent).toBe("ready");
    expect(screen.getByTestId("status-s-fail").textContent).toBe("failed");
  });

  it("offers Start ingestion only for uploaded sources", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, mixed),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Uploaded Book");

    // Exactly one Start control — on the sole uploaded row.
    const startButtons = screen.getAllByRole("button", {
      name: "Start ingestion",
    });
    expect(startButtons).toHaveLength(1);
    expect(
      screen.getByTestId("status-s-up").closest("li")?.querySelector("button")
        ?.textContent,
    ).toBe("Start ingestion");

    // Active/terminal rows offer no start action. (The ready row carries its
    // own "View structure" control (T13), so assert specifically that no row
    // but the uploaded one offers "Start ingestion".)
    for (const id of ["s-proc", "s-ready", "s-fail"]) {
      expect(
        screen.getByTestId(`status-${id}`).closest("li")?.textContent,
      ).not.toContain("Start ingestion");
    }
  });

  it("starts ingestion through the proxy and reflects processing on success", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[0]]),
      "POST /api/sources/s-up/ingestion": () =>
        jsonResponse(202, ingestionQueued),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SourcesPanel />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    // Row reflects processing and the start control is gone (no double-start).
    await waitFor(() =>
      expect(screen.getByTestId("status-s-up").textContent).toBe("processing"),
    );
    expect(
      screen.queryByRole("button", { name: "Start ingestion" }),
    ).toBeNull();

    // The proxy POST was issued to the same-origin ingestion path.
    const posted = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(posted?.[0]).toBe("/api/sources/s-up/ingestion");
  });

  it("shows Starting… + disables the button in flight and blocks a double-start", async () => {
    // The whole point of the SPEC_DEVIATION / lesson L-004 (keep the button
    // mounted + disabled rather than an optimistic flip) is that the in-flight
    // state is observable/testable. Drive it with a POST that resolves only when
    // we say so, so the intermediate frame is actually asserted.
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

    render(<SourcesPanel />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    // In flight: label flips to "Starting…" and the button is disabled.
    const starting = (await screen.findByRole("button", {
      name: "Starting…",
    })) as HTMLButtonElement;
    expect(starting.disabled).toBe(true);

    // Clicking the disabled button issues no second POST (no double-start).
    fireEvent.click(starting);
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);

    // Resolve the request → the row reaches processing and the control is gone.
    resolvePost(jsonResponse(202, ingestionQueued));
    await waitFor(() =>
      expect(screen.getByTestId("status-s-up").textContent).toBe("processing"),
    );
  });

  it("surfaces the error and keeps the row uploaded when the start is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[0]]),
        "POST /api/sources/s-up/ingestion": () =>
          jsonResponse(409, { detail: "Ingestion is already in progress." }),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Uploaded Book");

    fireEvent.click(screen.getByRole("button", { name: "Start ingestion" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Ingestion is already in progress.");
    // Row did NOT flip to processing; the start control remains.
    expect(screen.getByTestId("status-s-up").textContent).toBe("uploaded");
    expect(
      screen.getByRole("button", { name: "Start ingestion" }),
    ).toBeTruthy();
  });
});

describe("SourcesPanel structure view (T13)", () => {
  it("offers View structure only on ready rows", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, mixed),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    // Exactly one View-structure control — on the sole ready row.
    const viewButtons = screen.getAllByRole("button", {
      name: "View structure",
    });
    expect(viewButtons).toHaveLength(1);
    expect(
      screen.getByTestId("status-s-ready").closest("li")?.textContent,
    ).toContain("View structure");

    // Uploaded/processing/failed rows offer no structure control.
    for (const id of ["s-up", "s-proc", "s-fail"]) {
      expect(
        screen.getByTestId(`status-${id}`).closest("li")?.textContent,
      ).not.toContain("View structure");
    }
  });

  it("renders the metadata line and nested section tree under the row", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(200, readyStructure),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "View structure" }));

    // All section titles render.
    expect(await screen.findByText("Section 1.1")).toBeTruthy();
    expect(screen.getByText("Chapter 1")).toBeTruthy();
    expect(screen.getByText("Chapter 2")).toBeTruthy();

    // Nesting: the child sits inside its parent's <li> subtree, not at the root.
    const chapter1Li = screen.getByText("Chapter 1").closest("li");
    expect(chapter1Li).toBeTruthy();
    expect(within(chapter1Li!).getByText("Section 1.1")).toBeTruthy();
    // Its sibling root chapter is NOT inside Chapter 1's subtree.
    expect(within(chapter1Li!).queryByText("Chapter 2")).toBeNull();
    expect(chapter1Li!.querySelector("ul")).toBeTruthy();

    // Metadata line carries title/authors/language.
    const panel = screen.getByTestId("structure-s-ready");
    expect(panel.textContent).toContain("Ada Lovelace");
    expect(panel.textContent).toContain("en");
  });

  it("renders null metadata gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(200, {
            title: null,
            authors: [],
            language: null,
            sections: [],
          }),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "View structure" }));

    // The panel opens without crashing on the missing metadata.
    const panel = await screen.findByTestId("structure-s-ready");
    expect(panel).toBeTruthy();
    expect(panel.textContent).toContain("Untitled");
    expect(panel.textContent).toContain("Unknown author");
  });

  it("disables View structure while the structure fetch is in flight", async () => {
    let resolveGet!: (r: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveGet = resolve;
    });
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
      "GET /api/sources/s-ready/structure": () => pending,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "View structure" }));

    // In flight: label flips to "Loading…" and the button is disabled.
    const loading = (await screen.findByRole("button", {
      name: "Loading…",
    })) as HTMLButtonElement;
    expect(loading.disabled).toBe(true);

    // Clicking the disabled button issues no second structure GET.
    fireEvent.click(loading);
    const structureGets = fetchMock.mock.calls.filter(
      ([url]) => url === "/api/sources/s-ready/structure",
    );
    expect(structureGets).toHaveLength(1);

    // Resolving the request opens the panel.
    resolveGet(jsonResponse(200, readyStructure));
    expect(await screen.findByText("Chapter 1")).toBeTruthy();
  });

  it("shows an alert and re-enables the control when the fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(404, { detail: "That source has no structure yet." }),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "View structure" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("That source has no structure yet.");
    // No panel, and the control is back to "View structure" and enabled.
    expect(screen.queryByTestId("structure-s-ready")).toBeNull();
    const btn = screen.getByRole("button", {
      name: "View structure",
    }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("collapses the panel and drops its content when toggled again", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [mixed[2]]),
        "GET /api/sources/s-ready/structure": () =>
          jsonResponse(200, readyStructure),
      }),
    );

    render(<SourcesPanel />);
    await screen.findByText("Ready Book");

    fireEvent.click(screen.getByRole("button", { name: "View structure" }));
    expect(await screen.findByText("Chapter 1")).toBeTruthy();

    // Toggle again → the panel and its section titles are removed.
    fireEvent.click(screen.getByRole("button", { name: "Hide structure" }));
    expect(screen.queryByText("Chapter 1")).toBeNull();
    expect(screen.queryByTestId("structure-s-ready")).toBeNull();
    expect(
      screen.getByRole("button", { name: "View structure" }),
    ).toBeTruthy();
  });
});
