// @vitest-environment jsdom

/**
 * C gate (component) — the app shell header shows the signed-in email plus an
 * account link, logout, and theme toggle; logout and a 401 from `/me` both
 * redirect to /login; the theme toggle flips the `dark` class on <html>; the
 * `(app)` layout wraps pages in the sidebar shell while the `(auth)` layout
 * renders shell-free (FE-02/FE-03/FE-05).
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppLayout from "../app/(app)/layout";
import AuthLayout from "../app/(auth)/layout";
import { AuthHeader } from "../app/components/shell/auth-header";
import { ThemeProvider } from "../app/components/theme-provider";
import { SidebarProvider } from "../components/ui/sidebar";

const { routerReplace } = vi.hoisted(() => ({ routerReplace: vi.fn() }));

vi.mock("next/navigation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/navigation")>();
  return {
    ...actual,
    useRouter: () => ({
      replace: routerReplace,
      push: vi.fn(),
      prefetch: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      refresh: vi.fn(),
    }),
  };
});

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`; fail loudly on anything unexpected. */
function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

function sourceRow(id: string, title: string, status: string) {
  return {
    id,
    title,
    filename: `${id}.epub`,
    byte_size: 3,
    content_type: "application/epub+zip",
    status,
    created_at: "now",
  };
}

function renderHeader() {
  return render(
    <SidebarProvider>
      <AuthHeader />
    </SidebarProvider>,
  );
}

beforeEach(() => {
  routerReplace.mockClear();
  window.localStorage.clear();
  document.documentElement.className = "";
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AuthHeader", () => {
  it("shows the signed-in email plus account, logout, and theme controls", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/auth/me": () => authedMe.clone() }),
    );

    renderHeader();

    expect(await screen.findByText("a@b.c")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Account" }).getAttribute("href")).toBe(
      "/account",
    );
    expect(screen.getByRole("button", { name: "Log out" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Toggle theme" })).toBeTruthy();
  });

  it("logout carries X-CSRF-Token and redirects to /login", async () => {
    const fetchMock = routedFetch({
      "GET /api/auth/me": () => authedMe.clone(),
      "POST /api/auth/logout": () => new Response(null, { status: 204 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderHeader();
    await screen.findByText("a@b.c");

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    const logoutCall = fetchMock.mock.calls.find((c) => c[0] === "/api/auth/logout");
    expect(logoutCall).toBeDefined();
    const headers = new Headers(logoutCall![1]?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("flips the dark class on <html> when the theme toggle is clicked", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/auth/me": () => authedMe.clone() }),
    );

    render(
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <SidebarProvider>
          <AuthHeader />
        </SidebarProvider>
      </ThemeProvider>,
    );
    await screen.findByText("a@b.c");

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Toggle theme" }));
    });

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("theme")).toBe("dark");
  });

  it("redirects to /login and shows no email when /me returns 401", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/auth/me": () => new Response(null, { status: 401 }) }),
    );

    renderHeader();

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("a@b.c")).toBeNull();
  });
});

describe("app shell composition", () => {
  it("wraps (app) pages in the sidebar shell with the header", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "GET /api/auth/me": () => authedMe.clone(),
        "GET /api/sources": () => jsonResponse(200, [sourceRow("s1", "Ready Book", "ready")]),
      }),
    );

    render(
      <AppLayout>
        <div data-testid="page-content">Page body</div>
      </AppLayout>,
    );

    // Header (email) and sidebar (Library group) both frame the page content.
    expect(await screen.findByText("a@b.c")).toBeTruthy();
    expect(screen.getByText("Library")).toBeTruthy();
    expect(screen.getByTestId("page-content")).toBeTruthy();
  });

  it("renders the (auth) layout shell-free (no sidebar)", () => {
    render(
      <AuthLayout>
        <div data-testid="auth-child">Auth body</div>
      </AuthLayout>,
    );

    expect(screen.getByTestId("auth-child")).toBeTruthy();
    // No library sidebar around auth pages.
    expect(screen.queryByText("Library")).toBeNull();
  });
});
