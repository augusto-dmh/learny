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

  it("drops content-encoding and content-length from the relayed response", () => {
    // undici's fetch has already decompressed the upstream body; relaying the
    // original encoding/length headers would describe bytes the browser never
    // receives and corrupts the response once upstream compression is enabled.
    const upstream = new Response('{"ok":true}', {
      status: 200,
      headers: {
        "content-type": "application/json",
        "content-encoding": "gzip",
        "content-length": "999",
      },
    });

    const relayed = relayResponse(upstream);

    expect(relayed.headers.get("content-encoding")).toBeNull();
    expect(relayed.headers.get("content-length")).toBeNull();
    expect(relayed.headers.get("content-type")).toBe("application/json");
  });
});

describe("relayResponse — SSE stream relay (FE-22)", () => {
  it("relays a streamed SSE body unbuffered while keeping streaming headers and stripping encoding/length", async () => {
    const encoder = new TextEncoder();
    const decoder = new TextDecoder();

    // A body we drive by hand so we can observe the first chunk on the relayed
    // side *before* the upstream stream is closed — proving relayResponse hands
    // the stream through rather than buffering it to completion.
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
      },
    });
    const upstream = new Response(body, {
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "x-vercel-ai-ui-message-stream": "v1",
        "cache-control": "no-cache",
        "x-accel-buffering": "no",
        "content-encoding": "gzip",
        "content-length": "999",
      },
    });

    const relayed = relayResponse(upstream);

    // The three streaming headers survive; the wire-encoding headers are stripped.
    expect(relayed.headers.get("content-type")).toBe("text/event-stream");
    expect(relayed.headers.get("x-vercel-ai-ui-message-stream")).toBe("v1");
    expect(relayed.headers.get("cache-control")).toBe("no-cache");
    expect(relayed.headers.get("x-accel-buffering")).toBe("no");
    expect(relayed.headers.get("content-encoding")).toBeNull();
    expect(relayed.headers.get("content-length")).toBeNull();

    const reader = relayed.body!.getReader();

    // Enqueue only the first chunk, then read it off the relayed body while the
    // upstream stream is still open — if relayResponse buffered, this would hang.
    controller.enqueue(encoder.encode("data: chunk-1\n\n"));
    const first = await reader.read();
    expect(first.done).toBe(false);
    expect(decoder.decode(first.value)).toContain("chunk-1");

    // Now enqueue the second chunk and close — the reader keeps draining in order.
    controller.enqueue(encoder.encode("data: chunk-2\n\n"));
    controller.close();
    const second = await reader.read();
    expect(decoder.decode(second.value)).toContain("chunk-2");
    const end = await reader.read();
    expect(end.done).toBe(true);
  });
});
