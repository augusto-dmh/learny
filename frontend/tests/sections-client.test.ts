/**
 * FE-14/FE-15 — the section-content client reads one section by anchor through
 * the same-origin proxy.
 *
 * Verifies getSection GETs `/api/sources/{id}/section?anchor=<enc>` with the
 * anchor `encodeURIComponent`-encoded exactly once (proving a `href#fragment`
 * anchor round-trips without double-encoding), parses the `SectionView` on 200,
 * returns a typed `not_found` result on 404 (never throwing — the reader renders
 * it as a not-found state), and throws a readable error on other non-OK
 * responses (401). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import { getSection, type SectionView } from "../app/lib/sections";

// A real anchor: `href` path (`/`) plus fragment (`#`) — both reserved characters.
const ANCHOR = "text/ch1.xhtml#s2";

const section: SectionView = {
  anchor: ANCHOR,
  title: "Section Two",
  section_path: ["Chapter 1", "Section Two"],
  markdown: "## Section Two\n\nBody text.",
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

describe("section content client (FE-14/FE-15)", () => {
  it("GETs the section with the anchor URL-encoded exactly once and parses the view", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, section));

    const result = await getSection(
      "s1",
      ANCHOR,
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "found", section });
    const [url, init] = fetchMock.mock.calls[0];
    // Encoded once: `/`→`%2F`, `#`→`%23`. Not double-encoded (`%252F`).
    expect(url).toBe("/api/sources/s1/section?anchor=text%2Fch1.xhtml%23s2");
    expect(url).not.toContain("%25");
    // Decoding the query param yields back the exact anchor.
    expect(new URL(`http://x${url}`).searchParams.get("anchor")).toBe(ANCHOR);
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("returns a typed not-found result on 404 without throwing", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(404, { detail: "Section not found." }),
    );

    const result = await getSection(
      "s1",
      ANCHOR,
      fetchMock as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "not_found" });
  });

  it("throws a readable error when unauthenticated (401)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    await expect(
      getSection("s1", ANCHOR, fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Not authenticated.");
  });
});
