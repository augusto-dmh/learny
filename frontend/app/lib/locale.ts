/**
 * Browser-side interface-language client.
 *
 * The backend stores the learner's choice (`PUT`/`DELETE /api/me/locale`, read
 * back as `locale` on `/api/auth/me`); the `learny_locale` cookie is only the
 * render-time cache the root layout reads, so the server render never waits on a
 * backend call. The cookie is written here, by the client, after the backend has
 * accepted the change — never before, so a refused save leaves the interface in
 * the language it was in. Anonymous visitors have no stored choice and switch with
 * the cookie alone.
 */
import { LOCALE_COOKIE, isLocale, type AppLocale } from "@/i18n/config";

import { apiErrorFrom } from "./errors";

/** One year, matching the cookie shape the plan fixed (door 3). */
const COOKIE_MAX_AGE_SECONDS = 31536000;

/** Store the caller's interface language (200 `{locale}`); throws `ApiError`. */
export async function putLocale(
  locale: AppLocale,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AppLocale> {
  const res = await fetchImpl("/api/me/locale", {
    method: "PUT",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ locale }),
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "localeSave");
  }
  const body = (await res.json()) as { locale: string };
  return isLocale(body.locale) ? body.locale : locale;
}

/** Unset the caller's choice, back to "automatic" (204, idempotent); throws `ApiError`. */
export async function deleteLocale(
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl("/api/me/locale", {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "localeReset");
  }
}

/** The cookie's current value when it names a supported locale, else null. */
export function readLocaleCookie(doc: Document = document): AppLocale | null {
  for (const pair of doc.cookie.split(";")) {
    const [name, ...rest] = pair.trim().split("=");
    if (name === LOCALE_COOKIE) {
      const value = decodeURIComponent(rest.join("="));
      return isLocale(value) ? value : null;
    }
  }
  return null;
}

/** Write the render-time cache, or clear it (`null`) to fall back to negotiation. */
export function writeLocaleCookie(locale: AppLocale | null, doc: Document = document): void {
  doc.cookie =
    locale === null
      ? `${LOCALE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`
      : `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
}
