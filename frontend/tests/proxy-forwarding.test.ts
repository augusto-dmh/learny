/**
 * D1 gate — same-origin proxy live forwarding (ADR-017, AD-007, AC-2).
 *
 * Verifies the proxy forwards the session cookie and `X-CSRF-Token` header
 * unchanged, forwards/sets an `Origin` FastAPI will accept, and relays the
 * upstream `Set-Cookie` (with `HttpOnly` intact) and status back to the browser
 * without ever exposing the session token to client JS.
 */

import { describe, expect, it } from "vitest";

import { buildProxyRequest, relayResponse } from "../app/lib/proxy";

const API_BASE = "http://api.internal:8000";
const APP_ORIGIN = "http://localhost:3000";

describe("buildProxyRequest — auth header forwarding (D1)", () => {
  it("forwards the session cookie and X-CSRF-Token unchanged on a write", () => {
    const incoming = new Request("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: {
        cookie: "learny_session=opaque-token",
        "x-csrf-token": "csrf-abc",
        origin: APP_ORIGIN,
      },
    });
    const out = buildProxyRequest(incoming, ["auth", "logout"], API_BASE, APP_ORIGIN);
    expect(out.headers.get("cookie")).toBe("learny_session=opaque-token");
    expect(out.headers.get("x-csrf-token")).toBe("csrf-abc");
  });

  it("forwards the browser's Origin unchanged when present", () => {
    const incoming = new Request("http://localhost:3000/api/auth/login", {
      method: "POST",
      headers: { origin: APP_ORIGIN },
    });
    const out = buildProxyRequest(incoming, ["auth", "login"], API_BASE, APP_ORIGIN);
    expect(out.headers.get("origin")).toBe(APP_ORIGIN);
  });

  it("sets the configured app Origin when the browser omits it", () => {
    const incoming = new Request("http://localhost:3000/api/auth/login", {
      method: "POST",
    });
    expect(incoming.headers.has("origin")).toBe(false);
    const out = buildProxyRequest(incoming, ["auth", "login"], API_BASE, APP_ORIGIN);
    expect(out.headers.get("origin")).toBe(APP_ORIGIN);
  });
});

describe("relayResponse — upstream response relay (D1, AC-2)", () => {
  it("relays status and Set-Cookie with HttpOnly preserved end-to-end", () => {
    const upstream = new Response(JSON.stringify({ id: "u1", email: "a@b.c" }), {
      status: 201,
      headers: {
        "content-type": "application/json",
        "set-cookie":
          "learny_session=opaque-token; Path=/; HttpOnly; Secure; SameSite=Lax",
      },
    });

    const relayed = relayResponse(upstream);

    expect(relayed.status).toBe(201);
    const cookies = relayed.headers.getSetCookie();
    expect(cookies).toHaveLength(1);
    expect(cookies[0]).toContain("learny_session=opaque-token");
    expect(cookies[0]).toMatch(/HttpOnly/i);
  });

  it("does not expose the session token to client JS (HttpOnly only via Set-Cookie)", () => {
    const upstream = new Response(JSON.stringify({ id: "u1", email: "a@b.c" }), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "set-cookie":
          "learny_session=secret-token; Path=/; HttpOnly; Secure; SameSite=Lax",
      },
    });

    const relayed = relayResponse(upstream);

    // The body the browser's JS can read carries no session token.
    return relayed.text().then((body) => {
      expect(body).not.toContain("secret-token");
      // The only place the token appears is the HttpOnly Set-Cookie header,
      // which the browser stores out of reach of document.cookie / fetch JSON.
      const cookies = relayed.headers.getSetCookie();
      expect(cookies[0]).toContain("secret-token");
      expect(cookies[0]).toMatch(/HttpOnly/i);
    });
  });

  it("preserves multiple Set-Cookie headers as distinct cookies", () => {
    const upstream = new Response(null, { status: 204 });
    upstream.headers.append("set-cookie", "learny_session=; Path=/; HttpOnly; Max-Age=0");
    upstream.headers.append("set-cookie", "other=1; Path=/");

    const relayed = relayResponse(upstream);

    expect(relayed.status).toBe(204);
    expect(relayed.headers.getSetCookie()).toHaveLength(2);
  });
});
