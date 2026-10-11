// @vitest-environment jsdom

/**
 * The anonymous switcher changes language with the cookie alone: no API call,
 * the cookie shape the plan fixed, and a `router.refresh()` re-render that never
 * reloads the page (so a half-filled form survives).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleSwitcher } from "@/app/components/locale-switcher";
import { writeLocaleCookie } from "@/app/lib/locale";

import { setTestLocale } from "./setup-intl";

const ROOT = `${resolve(__dirname, "..")}/`;

const nav = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: nav.refresh, push: vi.fn(), replace: vi.fn() }),
}));

/** Capture every `document.cookie` write verbatim (jsdom drops the attributes on read). */
function spyOnCookieWrites(): string[] {
  const writes: string[] = [];
  const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie")!;
  vi.spyOn(document, "cookie", "set").mockImplementation((value: string) => {
    writes.push(value);
    descriptor.set!.call(document, value);
  });
  return writes;
}

beforeEach(() => {
  nav.refresh.mockReset();
  writeLocaleCookie(null);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("LocaleSwitcher", () => {
  it("sets the cookie without an API call", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const writes = spyOnCookieWrites();
    render(<LocaleSwitcher />);

    const select = screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement;
    expect(select.value).toBe("en");
    expect([...select.options].map((option) => option.text)).toEqual([
      "English",
      "Português (Brasil)",
    ]);

    fireEvent.change(select, { target: { value: "pt-BR" } });

    expect(writes).toEqual(["learny_locale=pt-BR; Path=/; Max-Age=31536000; SameSite=Lax"]);
    expect(document.cookie).toContain("learny_locale=pt-BR");
    expect(nav.refresh).toHaveBeenCalledTimes(1);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("labels itself in the active locale and ignores a no-op pick", () => {
    setTestLocale("pt-BR");
    const writes = spyOnCookieWrites();
    render(<LocaleSwitcher />);
    const select = screen.getByRole("combobox", { name: "Idioma" }) as HTMLSelectElement;
    expect(select.value).toBe("pt-BR");
    fireEvent.change(select, { target: { value: "pt-BR" } });
    expect(writes).toEqual([]);
    expect(nav.refresh).not.toHaveBeenCalled();
  });

  it("never reloads the page", () => {
    const reload = vi.fn();
    const assign = vi.fn();
    const replace = vi.fn();
    const original = window.location;
    let hrefWrites = 0;
    const fakeLocation = {
      ...original,
      reload,
      assign,
      replace,
      get href() {
        return original.href;
      },
      set href(_value: string) {
        hrefWrites += 1;
      },
    };
    vi.stubGlobal("location", fakeLocation);
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      render(<LocaleSwitcher />);
      fireEvent.change(screen.getByRole("combobox"), { target: { value: "pt-BR" } });
      expect(nav.refresh).toHaveBeenCalledTimes(1);
      expect(reload).not.toHaveBeenCalled();
      expect(assign).not.toHaveBeenCalled();
      expect(replace).not.toHaveBeenCalled();
      expect(hrefWrites).toBe(0);
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }

    // Every locale-change path (anonymous switcher, Account, the /me reconcile)
    // re-renders through the router; none touches `location` at all.
    for (const file of [
      "app/components/locale-switcher.tsx",
      "app/components/AccountPanel.tsx",
      "app/(app)/account/page.tsx",
      "app/components/use-locale-sync.ts",
      "app/lib/locale.ts",
    ]) {
      const code = readFileSync(`${ROOT}${file}`, "utf8");
      expect(code, file).not.toMatch(/\blocation\s*\.\s*(reload|assign|replace|href)\b|\blocation\s*=/);
    }
  });
});
