// @vitest-environment jsdom

/**
 * Account's language choice is confirm-then-move: the backend stores it first,
 * and only a confirmed save writes the render-time cookie and re-renders through
 * `router.refresh()`. "Automatic" clears both; a failed save changes nothing and
 * says so in the learner's language.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "@/app/(app)/account/page";
import { readLocaleCookie, writeLocaleCookie } from "@/app/lib/locale";

import { setTestLocale } from "./setup-intl";

const nav = vi.hoisted(() => ({ refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: nav.refresh, replace: nav.replace, push: vi.fn() }),
}));

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`, recording the order of calls and cookie state. */
function routedFetch(handlers: Record<string, Handler>, log: string[]) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    log.push(`${key} cookie=${readLocaleCookie() ?? "none"}`);
    return handler(init ?? {});
  });
}

function me(locale: string | null) {
  return () =>
    jsonResponse(200, {
      id: "u1",
      email: "a@b.c",
      created_at: "now",
      csrf_token: "csrf-xyz",
      ai_profile_id: null,
      locale,
    });
}

function baseHandlers(locale: string | null, overrides: Record<string, Handler> = {}) {
  return {
    "GET /api/auth/me": me(locale),
    "GET /api/ai/profiles": () => jsonResponse(200, []),
    "GET /api/me/ai-profile": () => jsonResponse(200, { profile_id: null }),
    ...overrides,
  };
}

async function renderAccount(handlers: Record<string, Handler>, log: string[] = []) {
  const fetchMock = routedFetch(handlers, log);
  vi.stubGlobal("fetch", fetchMock);
  render(<AccountPage />);
  await act(async () => {});
  return fetchMock;
}

function radio(name: string): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

beforeEach(() => {
  nav.refresh.mockReset();
  nav.replace.mockReset();
  writeLocaleCookie(null);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Account language", () => {
  it("saves then writes the cookie then refreshes", async () => {
    const log: string[] = [];
    const fetchMock = await renderAccount(
      baseHandlers(null, {
        "PUT /api/me/locale": () => {
          // The cookie is untouched while the save is in flight.
          expect(readLocaleCookie()).toBeNull();
          expect(nav.refresh).not.toHaveBeenCalled();
          return jsonResponse(200, { locale: "pt-BR" });
        },
      }),
      log,
    );
    expect(radio("Automatic (follow my browser)").checked).toBe(true);

    await act(async () => {
      fireEvent.click(radio("Português (Brasil)"));
    });

    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/me/locale");
    expect(JSON.parse(String(put[1]!.body))).toEqual({ locale: "pt-BR" });
    expect((put[1]!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-xyz");
    expect(log).toContain("PUT /api/me/locale cookie=none");
    expect(readLocaleCookie()).toBe("pt-BR");
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    expect(radio("Português (Brasil)").checked).toBe(true);
  });

  it("automatic clears the choice", async () => {
    writeLocaleCookie("pt-BR");
    const fetchMock = await renderAccount(
      baseHandlers("pt-BR", {
        "DELETE /api/me/locale": () => new Response(null, { status: 204 }),
      }),
    );
    expect(radio("Português (Brasil)").checked).toBe(true);
    // Stored and cookie already agree: loading the page did not refresh.
    expect(nav.refresh).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(radio("Automatic (follow my browser)"));
    });

    const del = fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE")!;
    expect(del[0]).toBe("/api/me/locale");
    expect((del[1]!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-xyz");
    expect(readLocaleCookie()).toBeNull();
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    expect(radio("Automatic (follow my browser)").checked).toBe(true);
  });

  it("failed save keeps the previous locale", async () => {
    for (const [locale, expected] of [
      ["en", "Could not save your language."],
      ["pt-BR", "Não foi possível salvar seu idioma."],
    ] as const) {
      setTestLocale(locale);
      writeLocaleCookie("en");
      await renderAccount(
        baseHandlers("en", {
          "PUT /api/me/locale": () =>
            jsonResponse(422, { detail: "locale must be one of: en, pt-BR" }),
        }),
      );
      nav.refresh.mockReset();

      await act(async () => {
        fireEvent.click(radio("Português (Brasil)"));
      });

      expect(readLocaleCookie()).toBe("en");
      expect(nav.refresh).not.toHaveBeenCalled();
      expect(radio("English").checked).toBe(true);
      expect(screen.getByRole("alert").textContent).toBe(expected);
      expect(screen.queryByText(/locale must be one of/)).toBeNull();
      cleanup();
    }
  });
});
