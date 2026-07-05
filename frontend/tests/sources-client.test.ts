/**
 * T7 gate (logic) — sources client calls the same-origin proxy (SRC-11).
 *
 * Verifies listSources/getSource/uploadSource target `/api/sources*` (never
 * cross-origin), that uploadSource sends a real multipart body (file + title)
 * and echoes the CSRF token in `X-CSRF-Token` (AD-007, mirroring auth.ts), and
 * that the parsed SourceSummary shape is preserved. No real network.
 */

import { describe, expect, it, vi } from "vitest";

import {
  getSource,
  listSources,
  uploadSource,
  type SourceSummary,
} from "../app/lib/sources";

const summary: SourceSummary = {
  id: "s1",
  title: "My Book",
  filename: "book.epub",
  byte_size: 1234,
  content_type: "application/epub+zip",
  status: "uploaded",
  created_at: "now",
};

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

describe("sources client (T7)", () => {
  it("listSources GETs the same-origin /api/sources and parses the summaries", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, [summary]));

    const sources = await listSources(fetchMock as unknown as typeof fetch);

    expect(sources).toEqual([summary]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("listSources returns an empty array when the user has no sources", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, []));
    await expect(
      listSources(fetchMock as unknown as typeof fetch),
    ).resolves.toEqual([]);
  });

  it("getSource GETs the same-origin /api/sources/{id} and parses the summary", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, summary));

    const source = await getSource("s1", fetchMock as unknown as typeof fetch);

    expect(source).toEqual(summary);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("uploadSource POSTs multipart (file + title) with the CSRF token to /api/sources", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(201, summary));
    const file = new File([new Uint8Array([1, 2, 3])], "book.epub", {
      type: "application/epub+zip",
    });

    const created = await uploadSource(
      file,
      "My Book",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(created).toEqual(summary);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    // The browser sets the multipart content-type + boundary itself; the client
    // must NOT hard-code it or the boundary is lost.
    expect(headers.has("content-type")).toBe(false);

    const body = init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("title")).toBe("My Book");
    const sent = body.get("file") as File;
    expect(sent).toBeInstanceOf(File);
    expect(sent.name).toBe("book.epub");
  });

  it("uploadSource surfaces the backend error detail on a rejected upload", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(415, { detail: "Only EPUB files are supported." }),
    );
    const file = new File([new Uint8Array([1])], "notes.txt", {
      type: "text/plain",
    });

    await expect(
      uploadSource(
        file,
        "Notes",
        "csrf-xyz",
        fetchMock as unknown as typeof fetch,
      ),
    ).rejects.toThrow("Only EPUB files are supported.");
  });
});
