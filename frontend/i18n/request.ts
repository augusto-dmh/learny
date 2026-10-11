import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { LOCALE_COOKIE, resolveLocale } from "./config";

/**
 * Per-request locale and catalog. No URL prefix and no middleware: the cookie
 * (the render-time cache of the learner's stored choice) wins, then
 * `Accept-Language`, then `en`. Catalogs load by locale name, so a further locale
 * is one `messages/<locale>.json` plus one entry in `LOCALES`.
 */
export default getRequestConfig(async () => {
  const [store, requestHeaders] = await Promise.all([cookies(), headers()]);
  const locale = resolveLocale({
    cookie: store.get(LOCALE_COOKIE)?.value,
    acceptLanguage: requestHeaders.get("accept-language"),
  });
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
