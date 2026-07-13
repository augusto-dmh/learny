import { describe, expect, it } from "vitest";

import { buildProxyRequest } from "../app/lib/proxy";

const API_BASE = "http://api.internal:8000";

describe("buildProxyRequest (ADR-017 same-origin proxy stub)", () => {
  it("forwards method and path to the configured API base", () => {
    const incoming = new Request("http://localhost:3000/api/auth/me", {
      method: "GET",
    });
    const out = buildProxyRequest(incoming, ["auth", "me"], API_BASE);
    expect(out.method).toBe("GET");
    expect(out.url).toBe("http://api.internal:8000/api/auth/me");
  });

  it("preserves the query string", () => {
    const incoming = new Request("http://localhost:3000/api/search?q=hello&n=2");
    const out = buildProxyRequest(incoming, ["search"], API_BASE);
    expect(out.url).toBe("http://api.internal:8000/api/search?q=hello&n=2");
  });

  it("forwards cookie and X-CSRF-Token headers unchanged", () => {
    const incoming = new Request("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: {
        cookie: "learny_session=opaque-token",
        "x-csrf-token": "csrf-123",
        "content-type": "application/json",
      },
    });
    const out = buildProxyRequest(incoming, ["auth", "logout"], API_BASE);
    expect(out.method).toBe("POST");
    expect(out.headers.get("cookie")).toBe("learny_session=opaque-token");
    expect(out.headers.get("x-csrf-token")).toBe("csrf-123");
    expect(out.headers.get("content-type")).toBe("application/json");
  });

  it("strips hop-by-hop headers (host)", () => {
    const incoming = new Request("http://localhost:3000/api/auth/me", {
      headers: { host: "localhost:3000", "x-keep": "yes" },
    });
    const out = buildProxyRequest(incoming, ["auth", "me"], API_BASE);
    expect(out.headers.get("host")).toBeNull();
    expect(out.headers.get("x-keep")).toBe("yes");
  });

  it("strips the Expect header so undici can send the upstream request", () => {
    // curl sends `Expect: 100-continue` on large multipart bodies; undici's
    // fetch rejects requests carrying it (UND_ERR_NOT_SUPPORTED), which turned
    // every large non-browser upload into a 500 (QA finding F3).
    const incoming = new Request("http://localhost:3000/api/sources", {
      method: "POST",
      headers: { expect: "100-continue", "content-type": "multipart/form-data" },
      body: "file-bytes",
      // @ts-expect-error duplex is required by undici for streamed bodies
      duplex: "half",
    });
    const out = buildProxyRequest(incoming, ["sources"], API_BASE);
    expect(out.headers.get("expect")).toBeNull();
    expect(out.headers.get("content-type")).toBe("multipart/form-data");
  });

  it("strips every hop-by-hop request header", () => {
    const incoming = new Request("http://localhost:3000/api/auth/me", {
      headers: {
        connection: "keep-alive",
        "keep-alive": "timeout=5",
        te: "trailers",
        trailer: "x-checksum",
        upgrade: "h2c",
        "proxy-authorization": "Basic xxx",
        "proxy-authenticate": "Basic",
        cookie: "learny_session=opaque-token",
      },
    });
    const out = buildProxyRequest(incoming, ["auth", "me"], API_BASE);
    for (const name of [
      "connection",
      "keep-alive",
      "te",
      "trailer",
      "upgrade",
      "proxy-authorization",
      "proxy-authenticate",
    ]) {
      expect(out.headers.get(name)).toBeNull();
    }
    expect(out.headers.get("cookie")).toBe("learny_session=opaque-token");
  });
});
