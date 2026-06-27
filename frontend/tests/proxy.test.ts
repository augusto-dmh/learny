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
});
