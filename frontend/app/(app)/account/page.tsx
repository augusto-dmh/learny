"use client";

/**
 * Authenticated landing area (D2).
 *
 * Shows the signed-in user, the language and AI-profile choices, and a logout
 * control. Unauthenticated visitors are redirected to `/login` — but this is a
 * UX convenience ONLY, NOT a security boundary: the data this page would render
 * comes from FastAPI, which enforces authentication and per-user ownership on
 * every protected endpoint regardless of client-side routing (FR-AUTH-007,
 * ADR-017). A confirmed language change re-renders through `router.refresh()`,
 * never a reload, so client state survives.
 */

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { AccountPanel } from "@/app/components/AccountPanel";

export default function AccountPage() {
  const t = useTranslations("account");
  const router = useRouter();
  return (
    <main>
      <h1>{t("pageTitle")}</h1>
      <AccountPanel
        onRequireAuth={() => router.replace("/login")}
        onLoggedOut={() => router.replace("/login")}
        onLocaleChanged={() => router.refresh()}
      />
    </main>
  );
}
