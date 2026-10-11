/**
 * The one place that knows which interface locales exist and how a request picks
 * one. Pure (no `next/*` imports) so the client switcher, the request config and
 * the tests all share it.
 *
 * `negotiateLocale` and the backend's `negotiate_locale` implement the same rule
 * over the same vector table (`backend/tests/test_locale.py`): order the header's
 * tags by q-value, then position; the first tag whose primary subtag is `pt` or
 * `en` decides, and any `pt` / `pt-*` maps to `pt-BR`.
 */

export const LOCALES = ["en", "pt-BR"] as const;
export type AppLocale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: AppLocale = "en";

/** The render-time cache of the learner's choice (the backend stays authoritative). */
export const LOCALE_COOKIE = "learny_locale";

const PRIMARY_SUBTAG_TO_LOCALE: Record<string, AppLocale> = {
  en: "en",
  pt: "pt-BR",
};

export function isLocale(value: unknown): value is AppLocale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Pick a supported locale from an `Accept-Language` header; `en` when none fits. */
export function negotiateLocale(acceptLanguage: string | null | undefined): AppLocale {
  if (!acceptLanguage) {
    return DEFAULT_LOCALE;
  }
  const ranked: { quality: number; position: number; tag: string }[] = [];
  acceptLanguage.split(",").forEach((part, position) => {
    const [rawTag, ...params] = part.split(";").map((piece) => piece.trim());
    if (!rawTag || rawTag === "*") {
      return;
    }
    const quality = qualityOf(params);
    if (quality === null || quality <= 0) {
      return;
    }
    ranked.push({ quality, position, tag: rawTag });
  });
  ranked.sort((a, b) => b.quality - a.quality || a.position - b.position);
  for (const { tag } of ranked) {
    const locale = PRIMARY_SUBTAG_TO_LOCALE[tag.split("-")[0].toLowerCase()];
    if (locale) {
      return locale;
    }
  }
  return DEFAULT_LOCALE;
}

/** The q-value among a tag's parameters (1 when absent); null when malformed. */
function qualityOf(params: string[]): number | null {
  for (const param of params) {
    const [name, value = ""] = param.split("=");
    if (name.trim().toLowerCase() === "q") {
      const parsed = Number(value);
      return value.trim() !== "" && Number.isFinite(parsed) ? parsed : null;
    }
  }
  return 1;
}

/** The locale a request renders: a valid cookie, else negotiation, else `en`. */
export function resolveLocale(input: {
  cookie?: string | null;
  acceptLanguage?: string | null;
}): AppLocale {
  if (isLocale(input.cookie)) {
    return input.cookie;
  }
  return negotiateLocale(input.acceptLanguage);
}
