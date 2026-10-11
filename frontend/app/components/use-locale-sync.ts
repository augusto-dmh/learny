"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { isLocale } from "@/i18n/config";
import type { AuthState } from "@/app/lib/auth";
import { readLocaleCookie, writeLocaleCookie } from "@/app/lib/locale";

/**
 * Bring the render-time cookie in line with the learner's stored locale.
 *
 * The backend wins: when `/api/auth/me` reports a supported `locale` that differs
 * from the `learny_locale` cookie (a new device, cleared cookies, a choice made
 * elsewhere), the cookie is rewritten and `refresh` re-renders the server tree in
 * the stored language. A `null` or unsupported stored value means "automatic", so
 * whatever the cookie or the browser negotiates stands and nothing refreshes.
 * Returns whether a refresh was requested.
 */
export function syncLocaleCookie(
  stored: string | null | undefined,
  refresh: () => void,
  doc: Document = document,
): boolean {
  if (!isLocale(stored) || readLocaleCookie(doc) === stored) {
    return false;
  }
  writeLocaleCookie(stored, doc);
  refresh();
  return true;
}

/**
 * Run {@link syncLocaleCookie} once per mount, as soon as the auth state is known.
 * `router.refresh()` keeps client state (unsent input, scroll position), and the
 * cookie then matches, so a second pass cannot refresh again.
 */
export function useLocaleSync(auth: AuthState | null): void {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
  const synced = useRef(false);

  useEffect(() => {
    if (synced.current || !auth || !auth.authenticated) {
      return;
    }
    synced.current = true;
    syncLocaleCookie(auth.user.locale, () => routerRef.current.refresh());
  }, [auth]);
}
