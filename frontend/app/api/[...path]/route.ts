/**
 * Catch-all same-origin proxy route (ADR-017).
 *
 * Forwards every `/api/*` browser request to FastAPI server-side, passing the
 * session cookie and `X-CSRF-Token` header through unchanged. No domain logic
 * lives here; FastAPI is authoritative for auth/authorization/product logic.
 */

import { buildProxyRequest } from "@/app/lib/proxy";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(req: Request, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  const upstreamReq = buildProxyRequest(req, path ?? []);
  const upstreamRes = await fetch(upstreamReq);

  // Pass the upstream response through unchanged (incl. Set-Cookie).
  const headers = new Headers(upstreamRes.headers);
  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers,
  });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
export const OPTIONS = handle;
