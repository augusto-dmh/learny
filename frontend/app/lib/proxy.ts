/**
 * Same-origin proxy helper (ADR-017).
 *
 * Pure, framework-light translation of an incoming browser request into an
 * outgoing request targeting the FastAPI backend. It forwards method, path,
 * query, headers (notably `cookie` and `x-csrf-token`), and body UNCHANGED.
 * It owns NO auth or domain logic — FastAPI remains authoritative.
 *
 * This cycle's stub: A2 ships the forwarding contract; D1 mounts it on the
 * live round-trip. Keeping the translation pure makes it unit-testable without
 * a running server.
 */

/** Resolve the FastAPI base URL from the (server-side) environment. */
export function getApiBase(): string {
  return process.env.LEARNY_API_BASE_URL ?? "http://localhost:8000";
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
