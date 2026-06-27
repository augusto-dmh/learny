/**
 * Catch-all same-origin proxy route (ADR-017).
 *
 * Forwards every `/api/*` browser request to FastAPI server-side, passing the
 * session cookie and `X-CSRF-Token` header through unchanged. No domain logic
 * lives here; FastAPI is authoritative for auth/authorization/product logic.
 *
 * The session cookie is `HttpOnly` end-to-end: FastAPI sets it with `HttpOnly`,
 * we relay the `Set-Cookie` header verbatim, and the browser stores it where
 * JS cannot read it. The proxy never copies the token into a JS-readable form.
 */

import { buildProxyRequest, relayResponse } from "@/app/lib/proxy";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(req: Request, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  const upstreamReq = buildProxyRequest(req, path ?? []);
  const upstreamRes = await fetch(upstreamReq);
  return relayResponse(upstreamRes);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
export const OPTIONS = handle;
