// @vitest-environment jsdom

/**
 * The signed-in client keeps the render-time cookie in line with the stored
 * locale: the backend wins when they differ (rewrite + exactly one refresh), and
 * "automatic" (`null`), an equal value or a failed `/api/auth/me` leave the cookie
 * and the page alone.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthState } from "@/app/lib/auth";
import { readLocaleCookie, writeLocaleCookie } from "@/app/lib/locale";
import { useLocaleSync } from "@/app/components/use-locale-sync";

const nav = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: nav.refresh, push: vi.fn(), replace: vi.fn() }),
}));

function signedIn(locale: string | null): AuthState {
  return {
    authenticated: true,
    user: {
      id: "u1",
      email: "a@b.c",
      created_at: "now",
      csrf_token: "csrf",
      ai_profile_id: null,
      locale,
    },
  };
}

function Probe({ auth }: { auth: AuthState | null }) {
  useLocaleSync(auth);
  return null;
}

beforeEach(() => {
  nav.refresh.mockReset();
  writeLocaleCookie(null);
});

afterEach(cleanup);

describe("useLocaleSync", () => {
  it("reconciles the cookie from the stored locale", () => {
    // Differs (no cookie yet) -> rewrite and refresh once, even across re-renders.
    const { rerender, unmount } = render(<Probe auth={null} />);
    expect(nav.refresh).not.toHaveBeenCalled();
    const stored = signedIn("pt-BR");
    rerender(<Probe auth={stored} />);
    expect(readLocaleCookie()).toBe("pt-BR");
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    rerender(<Probe auth={{ ...stored }} />);
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    unmount();

    // Differs (cookie holds the other locale) -> the backend wins.
    nav.refresh.mockReset();
    writeLocaleCookie("pt-BR");
    render(<Probe auth={signedIn("en")} />);
    expect(readLocaleCookie()).toBe("en");
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    cleanup();

    // Equal -> nothing to do.
    nav.refresh.mockReset();
    render(<Probe auth={signedIn("en")} />);
    expect(readLocaleCookie()).toBe("en");
    expect(nav.refresh).not.toHaveBeenCalled();
    cleanup();

    // Automatic (null) or an unsupported stored value -> the cookie stands.
    for (const locale of [null, "fr"]) {
      writeLocaleCookie("pt-BR");
      render(<Probe auth={signedIn(locale)} />);
      expect(readLocaleCookie(), String(locale)).toBe("pt-BR");
      cleanup();
    }
    writeLocaleCookie(null);
    render(<Probe auth={signedIn(null)} />);
    expect(readLocaleCookie()).toBeNull();
    expect(nav.refresh).not.toHaveBeenCalled();
    cleanup();

    // `/api/auth/me` failed or reported no session -> nothing happens.
    writeLocaleCookie("pt-BR");
    render(<Probe auth={{ authenticated: false }} />);
    expect(readLocaleCookie()).toBe("pt-BR");
    expect(nav.refresh).not.toHaveBeenCalled();
  });
});
