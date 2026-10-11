// @vitest-environment jsdom

/**
 * The stored locale actually reaches the signed-in entry points: the app-shell
 * header (every `(app)` route) and the immersive reader (outside the shell) both
 * run the cookie reconcile after their own `/api/auth/me` read. A stored value
 * that differs from the cookie rewrites it and refreshes exactly once; "automatic"
 * (`null`) leaves the cookie and the page alone.
 */

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterReader } from "@/app/components/chapter-reader";
import { AuthHeader } from "@/app/components/shell/auth-header";
import { readLocaleCookie, writeLocaleCookie } from "@/app/lib/locale";
import { SidebarProvider } from "@/components/ui/sidebar";

// One stable router object, as Next provides: AuthHeader's effect depends on it.
const nav = vi.hoisted(() => {
  const refresh = vi.fn();
  return { refresh, router: { refresh, replace: vi.fn(), push: vi.fn() } };
});
vi.mock("next/navigation", () => ({
  useRouter: () => nav.router,
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/sources/s1/read",
}));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** `/api/auth/me` answers with `locale`; every other request stays in flight. */
function stubBackend(locale: string | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/auth/me") {
        return jsonResponse(200, {
          id: "u1",
          email: "a@b.c",
          created_at: "now",
          csrf_token: "csrf",
          ai_profile_id: null,
          locale,
        });
      }
      return new Promise<Response>(() => {});
    }),
  );
}

const SURFACES = [
  {
    name: "app-shell header",
    render: () =>
      render(
        <SidebarProvider>
          <AuthHeader />
        </SidebarProvider>,
      ),
  },
  { name: "reader", render: () => render(<ChapterReader sourceId="s1" />) },
];

beforeEach(() => {
  nav.refresh.mockReset();
  writeLocaleCookie(null);
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("locale reconcile wiring", () => {
  it.each(SURFACES)("the $name rewrites a stale cookie from the stored locale", async (surface) => {
    writeLocaleCookie("en");
    stubBackend("pt-BR");
    surface.render();
    await act(async () => {});
    expect(readLocaleCookie()).toBe("pt-BR");
    expect(nav.refresh).toHaveBeenCalledTimes(1);
  });

  it.each(SURFACES)("the $name leaves an automatic choice alone", async (surface) => {
    writeLocaleCookie("pt-BR");
    stubBackend(null);
    surface.render();
    await act(async () => {});
    expect(readLocaleCookie()).toBe("pt-BR");
    expect(nav.refresh).not.toHaveBeenCalled();
  });
});
