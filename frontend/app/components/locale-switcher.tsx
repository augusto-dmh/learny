"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { LOCALES, isLocale } from "@/i18n/config";
import { writeLocaleCookie } from "@/app/lib/locale";
import { cn } from "@/lib/utils";

/**
 * The anonymous visitor's language control (landing and sign-in).
 *
 * There is no account to store the choice on, so it only writes the
 * `learny_locale` cookie and re-renders the server tree with `router.refresh()` —
 * no API call and no page reload, so a half-filled sign-in form survives. Signed-in
 * learners choose in Account instead, where the choice is stored.
 */
export function LocaleSwitcher({ className }: { className?: string }) {
  const t = useTranslations("common.locale");
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <select
      aria-label={t("label")}
      className={cn(
        "h-8 rounded-md border bg-background px-2 text-sm text-foreground",
        className,
      )}
      value={locale}
      disabled={pending}
      onChange={(event) => {
        const next = event.target.value;
        if (!isLocale(next) || next === locale) {
          return;
        }
        writeLocaleCookie(next);
        startTransition(() => router.refresh());
      }}
    >
      {LOCALES.map((option) => (
        <option key={option} value={option} lang={option}>
          {t(`names.${option}`)}
        </option>
      ))}
    </select>
  );
}
