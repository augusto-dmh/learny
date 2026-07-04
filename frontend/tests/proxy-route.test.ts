/**
 * D1 gate — the catch-all `/api/*` route wires buildProxyRequest/relayResponse
 * onto a live endpoint (ADR-017). The pure helpers are unit-tested elsewhere;
 * this covers the route glue: params resolution, forwarding to FastAPI, and
 * relaying status + Set-Cookie back unchanged.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "../app/api/[...path]/route";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("same-origin proxy route (ADR-017)", () => {
  it("POST forwards to FastAPI and relays status + Set-Cookie", async () => {
    const upstream = new Response(null, {
      status: 204,
      headers: { "set-cookie": "learny_session=abc; HttpOnly; Path=/" },
    });
    const fetchMock = vi.fn().mockResolvedValue(upstream);
    vi.stubGlobal("fetch", fetchMock);

    const req = new Request("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: { "x-csrf-token": "csrf-1" },
    });
    const res = await POST(req, {
      params: Promise.resolve({ path: ["auth", "logout"] }),
    });

    // Forwarded upstream with method + path preserved and the CSRF header carried.
    const forwarded = fetchMock.mock.calls[0][0] as Request;
    expect(forwarded.method).toBe("POST");
    expect(new URL(forwarded.url).pathname).toBe("/api/auth/logout");
    expect(forwarded.headers.get("x-csrf-token")).toBe("csrf-1");

    // Response relayed back unchanged, including Set-Cookie.
    expect(res.status).toBe(204);
    expect(res.headers.get("set-cookie")).toContain("learny_session=abc");
  });

  it("GET forwards without a body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const req = new Request("http://localhost:3000/api/auth/me", { method: "GET" });
    const res = await GET(req, { params: Promise.resolve({ path: ["auth", "me"] }) });

    const forwarded = fetchMock.mock.calls[0][0] as Request;
    expect(forwarded.method).toBe("GET");
    expect(forwarded.body).toBeNull();
    expect(res.status).toBe(200);
  });
});
