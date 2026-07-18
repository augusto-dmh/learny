/**
 * NF-11 gate (logic) — the notes + highlights client calls the same-origin proxy.
 *
 * Verifies each helper targets the right same-origin path with `credentials:
 * "same-origin"`, echoes the CSRF token in `X-CSRF-Token` on the state-changing
 * create/update/delete/capture calls (AD-007) and sends none on the reads, builds
 * the list query from the optional `tag` filter (percent-encoded), passes each
 * success payload (note detail with anchors, summaries with anchor statuses,
 * backlinks) through unchanged, and surfaces a typed `NoteError` on every
 * documented error status — mapping 409 → `stale_capture`, 422 → `body_too_long`,
 * anything else → `unknown` — preferring the backend `detail` with a readable
 * fallback for a 422 list detail or an unparseable body. No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  captureHighlight,
  createNote,
  deleteNote,
  getBacklinks,
  getNote,
  listNotes,
  NoteError,
  updateNote,
  type Backlink,
  type NoteDetail,
  type NoteSummary,
} from "../app/lib/notes";

const anchor = {
  id: "a1",
  source_id: "s1",
  source_title: "Ready Book",
  anchor: "chapter-1.xhtml#core-idea",
  section_path: ["Chapter 1", "Core Idea"],
  block_ordinal: 2,
  start_offset: 4,
  end_offset: 26,
  quote_exact: "wrote the first algorithm",
  quote_prefix: "Ada Lovelace ",
  quote_suffix: ".",
  status: "active",
};

const noteDetail: NoteDetail = {
  id: "n1",
  title: "Ada's algorithm",
  body_markdown: "A note about [[Babbage]].",
  tags: ["history"],
  anchors: [anchor],
  created_at: "now",
  updated_at: "now",
};

const summary: NoteSummary = {
  id: "n1",
  title: "Ada's algorithm",
  tags: ["history"],
  anchor_statuses: ["active", "orphaned"],
  created_at: "now",
  updated_at: "now",
};

const backlink: Backlink = { note_id: "n2", title: "Babbage" };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fetchMockFn(
  impl: (...args: [string, RequestInit]) => Promise<Response>,
) {
  return vi.fn<(...args: [string, RequestInit]) => Promise<Response>>(impl);
}

describe("createNote (NF-11)", () => {
  it("POSTs /api/notes with the CSRF token and passes the note through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, noteDetail));

    const result = await createNote(
      { title: "Ada's algorithm", body_markdown: "A note about [[Babbage]].", tags: ["history"] },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(noteDetail);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      title: "Ada's algorithm",
      body_markdown: "A note about [[Babbage]].",
      tags: ["history"],
    });
    // The anchor payload the detail screen renders survives the round-trip.
    expect(result.anchors[0].status).toBe("active");
    expect(result.anchors[0].source_id).toBe("s1");
  });

  it("raises a body_too_long NoteError on a 422 over-cap response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Note body is too long." }),
    );

    const err = await createNote(
      { title: "x" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("body_too_long");
    expect(err.status).toBe(422);
    expect(err.message).toBe("Note body is too long.");
  });

  it("falls back to a readable message when a 422 detail is a list, not a string", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, {
        detail: [{ type: "string_type", loc: ["body", "title"], msg: "str" }],
      }),
    );

    const err = await createNote(
      { title: "x" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("body_too_long");
    expect(err.message).toBe("Could not create the note.");
  });
});

describe("listNotes (NF-11)", () => {
  it("GETs /api/notes with no query and no CSRF, passing summaries through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, [summary]));

    const result = await listNotes({}, fetchMock as unknown as typeof fetch);

    expect(result).toEqual([summary]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
    // The badge inputs the list renders survive the round-trip.
    expect(result[0].anchor_statuses).toEqual(["active", "orphaned"]);
    expect(result[0].tags).toEqual(["history"]);
  });

  it("builds the tag filter query, percent-encoding the value", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, [summary]));

    await listNotes(
      { tag: "deep work" },
      fetchMock as unknown as typeof fetch,
    );

    expect(fetchMock.mock.calls[0][0]).toBe("/api/notes?tag=deep%20work");
  });

  it("defaults to no filter when called with no argument", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, [summary]));

    await listNotes(undefined, fetchMock as unknown as typeof fetch);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/notes");
  });

  it("surfaces an unknown NoteError on a 401 unauthenticated response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    const err = await listNotes(
      {},
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(401);
    expect(err.message).toBe("Not authenticated.");
  });
});

describe("getNote (NF-11)", () => {
  it("GETs /api/notes/{id} with no CSRF and passes the detail through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, noteDetail));

    const result = await getNote("n1", fetchMock as unknown as typeof fetch);

    expect(result).toEqual(noteDetail);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes/n1");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("surfaces an unknown NoteError on a 404 missing/non-owned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Note not found." }),
    );

    const err = await getNote("n1", fetchMock as unknown as typeof fetch).catch(
      (e) => e,
    );

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(404);
    expect(err.message).toBe("Note not found.");
  });
});

describe("updateNote (NF-11)", () => {
  it("PATCHes /api/notes/{id} with the CSRF token and body, passing the detail through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, noteDetail));

    const result = await updateNote(
      "n1",
      { title: "Ada's algorithm", body_markdown: "edited", tags: [] },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(noteDetail);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes/n1");
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual({
      title: "Ada's algorithm",
      body_markdown: "edited",
      tags: [],
    });
  });

  it("raises a body_too_long NoteError on a 422 over-cap response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Note body is too long." }),
    );

    const err = await updateNote(
      "n1",
      { title: "x" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("body_too_long");
    expect(err.message).toBe("Note body is too long.");
  });
});

describe("deleteNote (NF-11)", () => {
  it("DELETEs /api/notes/{id} with the CSRF token and resolves on 204", async () => {
    const fetchMock = fetchMockFn(async () => new Response(null, { status: 204 }));

    await expect(
      deleteNote("n1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes/n1");
    expect(init.method).toBe("DELETE");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("surfaces an unknown NoteError on a 404 missing/non-owned response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Note not found." }),
    );

    const err = await deleteNote(
      "n1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("unknown");
    expect(err.status).toBe(404);
  });
});

describe("getBacklinks (NF-11)", () => {
  it("GETs /api/notes/{id}/backlinks with no CSRF and passes them through", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, [backlink]));

    const result = await getBacklinks("n1", fetchMock as unknown as typeof fetch);

    expect(result).toEqual([backlink]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/notes/n1/backlinks");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
    expect(result[0].note_id).toBe("n2");
    expect(result[0].title).toBe("Babbage");
  });
});

describe("captureHighlight (NF-11)", () => {
  it("POSTs /api/sources/{id}/highlights with the CSRF token and selection payload", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, noteDetail));

    const payload = {
      anchor: "chapter-1.xhtml#core-idea",
      quote_exact: "wrote the first algorithm",
      quote_prefix: "Ada Lovelace ",
      quote_suffix: ".",
      title: "Ada's algorithm",
      body_markdown: "",
      tags: [],
    };
    const result = await captureHighlight(
      "s1",
      payload,
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual(noteDetail);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/highlights");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("raises a stale_capture NoteError on a 409 replaced-corpus response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "The book changed while you were reading." }),
    );

    const err = await captureHighlight(
      "s1",
      { anchor: "a", quote_exact: "q", title: "t" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("stale_capture");
    expect(err.status).toBe(409);
    expect(err.message).toBe("The book changed while you were reading.");
  });

  it("raises a body_too_long NoteError on a 422 over-cap response", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(422, { detail: "Note body is too long." }),
    );

    const err = await captureHighlight(
      "s1",
      { anchor: "a", quote_exact: "q", title: "t" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("body_too_long");
  });

  it("falls back to a readable message when the error body is not parseable", async () => {
    const fetchMock = fetchMockFn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    );

    const err = await captureHighlight(
      "s1",
      { anchor: "a", quote_exact: "q", title: "t" },
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e) => e);

    expect(err).toBeInstanceOf(NoteError);
    expect(err.kind).toBe("unknown");
    expect(err.message).toBe("Could not capture the highlight.");
  });
});
