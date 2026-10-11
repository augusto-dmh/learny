import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_COOKIE,
  isLocale,
  negotiateLocale,
  resolveLocale,
} from "@/i18n/config";

const root = fileURLToPath(new URL("..", import.meta.url));

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

  it("cookie beats Accept-Language", () => {
    expect(resolveLocale({ cookie: "en", acceptLanguage: "pt-BR,pt;q=0.9" })).toBe("en");
    expect(resolveLocale({ cookie: "pt-BR", acceptLanguage: "en-US" })).toBe("pt-BR");
  });

  it("ignores an unsupported cookie", () => {
    for (const cookie of ["fr", "pt", "PT-BR", "", undefined, null]) {
      expect(resolveLocale({ cookie, acceptLanguage: "pt-BR" }), String(cookie)).toBe("pt-BR");
      expect(resolveLocale({ cookie, acceptLanguage: "en-US" }), String(cookie)).toBe("en");
    }
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
