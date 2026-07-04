/**
 * Same-origin proxy helper (ADR-017).
 *
 * Pure, framework-light translation of an incoming browser request into an
 * outgoing request targeting the FastAPI backend. It forwards method, path,
 * query, headers (notably `cookie` and `x-csrf-token`), and body UNCHANGED.
 * It owns NO auth or domain logic — FastAPI remains authoritative.
 *
 * A2 shipped the forwarding contract; D1 mounts it on the live browser→proxy→
 * FastAPI round-trip. Keeping the translation pure makes it unit-testable
 * without a running server.
 *
 * Origin (AD-007): FastAPI's register/login/logout endpoints reject any
 * state-changing request whose Origin/Referer host is not in its trusted set
 * (`LEARNY_CSRF_TRUSTED_ORIGINS`). On a real same-origin browser POST the
 * browser already sends `Origin: <app origin>`, which we forward unchanged. We
 * additionally guarantee an acceptable Origin reaches the backend even when the
 * browser omits it, by falling back to the configured app origin
 * (`LEARNY_APP_ORIGIN`). This is a pure transport concern — no auth/domain
 * logic; FastAPI remains authoritative for the actual CSRF/Origin decision.
 */

/** Resolve the FastAPI base URL from the (server-side) environment. */
export function getApiBase(): string {
  return process.env.LEARNY_API_BASE_URL ?? "http://localhost:8000";
}

/**
 * Resolve the public origin this app is served from (server-side). Used as the
 * fallback `Origin` forwarded to FastAPI so its Origin/Referer CSRF gate passes
 * even when a browser omits the header. Must be a member of the backend's
 * `LEARNY_CSRF_TRUSTED_ORIGINS` for state-changing auth calls to succeed.
 */
export function getAppOrigin(): string {
  return process.env.LEARNY_APP_ORIGIN ?? "http://localhost:3000";
}

/**
 * Hop-by-hop headers that must not be forwarded across a proxy boundary
 * (RFC 7230 §6.1). `host` is dropped so the upstream sets its own.
 */
const STRIPPED_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-length",
]);

/**
 * Build the upstream request for a given incoming request and captured path
 * segments. `segments` are the `[...path]` parts after `/api/`.
 */
export function buildProxyRequest(
  req: Request,
  segments: string[],
  apiBase: string = getApiBase(),
  appOrigin: string = getAppOrigin(),
): Request {
  const incomingUrl = new URL(req.url);
  const upstreamPath = segments.map(encodeURIComponent).join("/");
  const target = new URL(`/api/${upstreamPath}`, apiBase);
  target.search = incomingUrl.search;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!STRIPPED_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  // Guarantee FastAPI's Origin/Referer CSRF gate sees a trusted origin (AD-007):
  // forward the browser's Origin when present (already copied above), otherwise
  // fall back to the configured app origin. No domain logic — pure transport.
  if (!headers.has("origin")) {
    headers.set("origin", appOrigin);
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  return new Request(target.toString(), {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    // Required by undici/Node fetch when streaming a request body.
    ...(hasBody ? { duplex: "half" } : {}),
    redirect: "manual",
  } as RequestInit);
}

/**
 * Relay a FastAPI response back to the browser unchanged: status, body, and all
 * headers — including every `Set-Cookie` verbatim so the `HttpOnly`, `Secure`,
 * `SameSite`, and `Path` attributes FastAPI set survive end-to-end (NFR-SEC-002,
 * AC-2). `Set-Cookie` is relayed via `getSetCookie()` so multiple cookies are
 * preserved as distinct headers rather than collapsed into one comma-joined value.
 */
export function relayResponse(upstream: Response): Response {
  const headers = new Headers(upstream.headers);

  // Re-emit Set-Cookie as discrete headers (a comma-join would corrupt
  // attributes like Expires). `getSetCookie` is available on undici/Node ≥18.5.
  const setCookies = upstream.headers.getSetCookie?.() ?? [];
  if (setCookies.length > 0) {
    headers.delete("set-cookie");
    for (const cookie of setCookies) {
      headers.append("set-cookie", cookie);
    }
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}
