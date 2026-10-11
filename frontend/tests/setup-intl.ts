/**
 * Test binding for next-intl.
 *
 * Components read copy through `useTranslations` / `getTranslations`, which need
 * a request context (server) or a provider (client). Wrapping ~80 test files in a
 * provider would bury every real change in churn, so the hooks are bound to
 * use-intl's real `createTranslator` / `createFormatter` over the shipped
 * catalogs: real ICU plurals, dates and rich text, no provider. The locale is
 * `en` unless a test calls `setTestLocale("pt-BR")`; it resets after each test.
 *
 * A missing key THROWS here, so a component that reads a key the catalog lacks
 * fails its own test instead of rendering a key path. One test
 * (`i18n-layout.test.tsx`) renders the real `NextIntlClientProvider` to cover the
 * wiring this binding replaces.
 */
import { createFormatter, createTranslator } from "use-intl/core";
import { afterEach, vi } from "vitest";

import type { AppLocale } from "@/i18n/config";
import en from "@/messages/en.json";
import ptBR from "@/messages/pt-BR.json";

const CATALOGS = { en, "pt-BR": ptBR } as const;

const state: { locale: AppLocale } = { locale: "en" };

export function setTestLocale(locale: AppLocale): void {
  state.locale = locale;
}

function failOnError(error: unknown): never {
  throw error;
}

function translator(namespace?: string) {
  return createTranslator({
    locale: state.locale,
    messages: CATALOGS[state.locale],
    namespace: namespace as never,
    onError: failOnError,
  });
}

function formatter() {
  return createFormatter({ locale: state.locale, onError: failOnError });
}

afterEach(() => {
  state.locale = "en";
});

vi.mock("next-intl", async (importActual) => {
  const actual = await importActual<typeof import("next-intl")>();
  return {
    ...actual,
    useTranslations: (namespace?: string) => translator(namespace),
    useLocale: () => state.locale,
    useFormatter: () => formatter(),
  };
});

vi.mock("next-intl/server", () => ({
  getTranslations: async (arg?: string | { namespace?: string }) =>
    translator(typeof arg === "string" ? arg : arg?.namespace),
  getLocale: async () => state.locale,
  getMessages: async () => CATALOGS[state.locale],
  getFormatter: async () => formatter(),
}));
