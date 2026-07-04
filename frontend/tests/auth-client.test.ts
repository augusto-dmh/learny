/**
 * D2 gate (logic) — browser auth client calls the same-origin proxy (AC-2/AC-3).
 *
 * Verifies register/login/logout/fetchAuthState target the `/api/*` proxy with
 * the right method/body, and that logout obtains the CSRF token from
 * `/api/auth/me` and echoes it in `X-CSRF-Token` (AD-007). No real network.
 */

import { describe, expect, it, vi } from "vitest";

import { fetchAuthState, login, logout, register } from "../app/lib/auth";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A `fetch`-shaped mock whose `.mock.calls` are typed as `[url, init]`. */
function fetchMockFn(
  impl: (...args: [string, RequestInit]) => Promise<Response>,
) {
  return vi.fn<(...args: [string, RequestInit]) => Promise<Response>>(impl);
}

describe("auth client (D2)", () => {
  it("register posts credentials to the proxy /api/auth/register", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(201, { id: "u1", email: "a@b.c", created_at: "now" }),
    );
    const user = await register("a@b.c", "pw", fetchMock as unknown as typeof fetch);

    expect(user.email).toBe("a@b.c");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/register");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@b.c", password: "pw" });
  });

  it("login posts credentials to the proxy /api/auth/login", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(200, { id: "u1", email: "a@b.c", created_at: "now" }),
    );
    await login("a@b.c", "pw", fetchMock as unknown as typeof fetch);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(init.method).toBe("POST");
  });

  it("login surfaces the backend error detail on failure", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(401, { detail: "Invalid credentials." }));
    await expect(
      login("a@b.c", "wrong", fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Invalid credentials.");
  });

  it("fetchAuthState maps 200 -> authenticated and 401 -> anonymous", async () => {
    const authed = vi.fn(async () =>
      jsonResponse(200, { id: "u1", email: "a@b.c", created_at: "now", csrf_token: "t" }),
    );
    const anon = vi.fn(async () => new Response(null, { status: 401 }));

    await expect(fetchAuthState(authed as unknown as typeof fetch)).resolves.toMatchObject({
      authenticated: true,
    });
    await expect(fetchAuthState(anon as unknown as typeof fetch)).resolves.toEqual({
      authenticated: false,
    });
  });

  it("logout with a provided CSRF token skips the /api/auth/me round-trip", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await logout("csrf-provided", fetchMock as unknown as typeof fetch);

    expect(fetchMock).toHaveBeenCalledTimes(1); // no /me probe
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/logout");
    expect(init.method).toBe("POST");
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-provided");
  });

  it("logout without a token fetches /api/auth/me then sends X-CSRF-Token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(200, {
          id: "u1",
          email: "a@b.c",
          created_at: "now",
          csrf_token: "csrf-xyz",
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await logout(undefined, fetchMock as unknown as typeof fetch);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/me");

    const [logoutUrl, logoutInit] = fetchMock.mock.calls[1];
    expect(logoutUrl).toBe("/api/auth/logout");
    expect(logoutInit.method).toBe("POST");
    const headers = new Headers(logoutInit.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("logout without a token is a no-op when already unauthenticated", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 401 }));
    await logout(undefined, fetchMock as unknown as typeof fetch);
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the /me probe
  });
});
