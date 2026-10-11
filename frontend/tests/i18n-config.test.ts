import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_COOKIE,
  isLocale,
  negotiateLocale,
  resolveLocale,
} from "@/i18n/config";

const root = fileURLToPath(new URL("..", import.meta.url));

// The per-request config is exercised for real: `next/headers` is stubbed per
// call and `getRequestConfig` hands back the config factory it wraps.
const request = vi.hoisted(() => ({
  cookie: undefined as string | undefined,
  acceptLanguage: null as string | null,
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "learny_locale" && request.cookie !== undefined
        ? { name, value: request.cookie }
        : undefined,
  }),
  headers: async () => ({
    get: (name: string) => (name === "accept-language" ? request.acceptLanguage : null),
  }),
}));
vi.mock("next-intl/server", () => ({
  getRequestConfig: (factory: unknown) => factory,
}));

/** Run `i18n/request.ts` for one request; returns the locale and catalog it picks. */
async function renderRequest(cookie: string | undefined, acceptLanguage: string | null) {
  request.cookie = cookie;
  request.acceptLanguage = acceptLanguage;
  const { default: factory } = (await import("@/i18n/request")) as unknown as {
    default: () => Promise<{ locale: string; messages: { common: { loading: string } } }>;
  };
  return factory();
}

// The shared vector table: backend/tests/test_locale.py::NEGOTIATION_VECTORS asserts
// the same inputs against the same outputs, so the two implementations cannot drift.
const NEGOTIATION_VECTORS: [string | null, string][] = [
  ["pt", "pt-BR"],
  ["pt-BR", "pt-BR"],
  ["pt-PT", "pt-BR"],
  ["pt;q=0.9,en;q=0.8", "pt-BR"],
  ["en,pt", "en"],
  ["en;q=0.5,pt;q=0.9", "pt-BR"],
  ["pt-BR,pt;q=0.9,en;q=0.8", "pt-BR"],
  ["en-US,en;q=0.9", "en"],
  ["fr,pt;q=0.5", "pt-BR"],
  [null, "en"],
  ["", "en"],
  [";;;", "en"],
  ["pt;q=abc", "en"],
  ["fr,de", "en"],
  ["*", "en"],
  ["pt;q=0", "en"],
];

describe("locale config", () => {
  it("supports exactly en and pt-BR", () => {
    expect([...LOCALES]).toEqual(["en", "pt-BR"]);
    expect(DEFAULT_LOCALE).toBe("en");
    expect(LOCALE_COOKIE).toBe("learny_locale");
    expect(isLocale("en")).toBe(true);
    expect(isLocale("pt-BR")).toBe(true);
    for (const bad of ["pt", "PT-BR", "fr", "", null, undefined, 3]) {
      expect(isLocale(bad)).toBe(false);
    }
  });

  it("negotiates pt-BR from Accept-Language by q-value then position", () => {
    for (const [header, expected] of NEGOTIATION_VECTORS) {
      expect(negotiateLocale(header), String(header)).toBe(expected);
    }
  });

  it("cookie beats Accept-Language", async () => {
    expect(resolveLocale({ cookie: "en", acceptLanguage: "pt-BR,pt;q=0.9" })).toBe("en");
    expect(resolveLocale({ cookie: "pt-BR", acceptLanguage: "en-US" })).toBe("pt-BR");

    // Through the real request config: the cookie decides, and its catalog loads.
    const english = await renderRequest("en", "pt-BR,pt;q=0.9");
    expect(english.locale).toBe("en");
    expect(english.messages.common.loading).toBe("Loading…");
    const portuguese = await renderRequest("pt-BR", "en-US");
    expect(portuguese.locale).toBe("pt-BR");
    expect(portuguese.messages.common.loading).toBe("Carregando…");
    // No cookie: Accept-Language decides.
    expect((await renderRequest(undefined, "pt-BR,pt;q=0.9,en;q=0.8")).locale).toBe("pt-BR");
    expect((await renderRequest(undefined, null)).locale).toBe("en");
  });

  it("ignores an unsupported cookie", async () => {
    for (const cookie of ["fr", "pt", "PT-BR", "", undefined, null]) {
      expect(resolveLocale({ cookie, acceptLanguage: "pt-BR" }), String(cookie)).toBe("pt-BR");
      expect(resolveLocale({ cookie, acceptLanguage: "en-US" }), String(cookie)).toBe("en");
    }

    // Through the real request config.
    expect((await renderRequest("fr", "en-US")).locale).toBe("en");
    expect((await renderRequest("fr", "pt-BR")).locale).toBe("pt-BR");
    expect((await renderRequest("PT-BR", "en")).locale).toBe("en");
  });

  it("falls back to en", () => {
    expect(resolveLocale({})).toBe("en");
    expect(resolveLocale({ cookie: "xx", acceptLanguage: ";;;" })).toBe("en");
    expect(resolveLocale({ acceptLanguage: "pt;q=abc" })).toBe("en");
    expect(resolveLocale({ acceptLanguage: "fr,de" })).toBe("en");
  });

  it("catalog files match LOCALES", () => {
    const files = readdirSync(`${root}messages`)
      .filter((name) => name.endsWith(".json"))
      .map((name) => name.replace(/\.json$/, ""))
      .sort();
    expect(files).toEqual([...LOCALES].sort());

    // The request config loads a catalog by locale name: no per-locale branch, so a
    // further locale is a catalog file plus a LOCALES entry and nothing else.
    const request = readFileSync(`${root}i18n/request.ts`, "utf8");
    expect(request).toContain("`../messages/${locale}.json`");
    for (const locale of LOCALES) {
      expect(request).not.toContain(`"${locale}"`);
    }
  });
});
