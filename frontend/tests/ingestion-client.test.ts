/**
 * T7 gate (logic) — the ingestion client starts a job through the same-origin
 * proxy (ING-10).
 *
 * Verifies startIngestion POSTs `/api/sources/{id}/ingestion` (never
 * cross-origin), echoes the CSRF token in `X-CSRF-Token` (AD-007, mirroring
 * uploadSource), parses the secret-free `IngestionSummary` (status/attempts/
 * error/ordered events), and surfaces the backend `detail` on 409/502. No real
 * network.
 */

import { describe, expect, it, vi } from "vitest";

import { startIngestion, type IngestionSummary } from "../app/lib/sources";

const summary: IngestionSummary = {
  id: "j1",
  status: "queued",
  attempts: 0,
  error: null,
  created_at: "now",
  updated_at: "now",
  events: [{ type: "queued", message: null, created_at: "now" }],
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

describe("ingestion client (T7)", () => {
  it("POSTs the same-origin /api/sources/{id}/ingestion with the CSRF token and parses the summary", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(202, summary));

    const started = await startIngestion(
      "s1",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(started).toEqual(summary);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sources/s1/ingestion");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");

    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("surfaces the backend detail when a job is already in progress (409)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(409, { detail: "Ingestion is already in progress." }),
    );

    await expect(
      startIngestion("s1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Ingestion is already in progress.");
  });

  it("surfaces the backend detail when the enqueue fails (502)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(502, { detail: "Could not start ingestion." }),
    );

    await expect(
      startIngestion("s1", "csrf-xyz", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Could not start ingestion.");
  });
});
