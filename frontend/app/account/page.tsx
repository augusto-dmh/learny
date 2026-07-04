"use client";

/**
 * Authenticated landing area (D2).
 *
 * Shows the signed-in user and a logout control. Unauthenticated visitors are
 * redirected to `/login` — but this is a UX convenience ONLY, NOT a security
 * boundary: the data this page would render comes from FastAPI, which enforces
 * authentication and per-user ownership on every protected endpoint regardless
 * of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useRouter } from "next/navigation";

import { AccountPanel } from "@/app/components/AccountPanel";

export default function AccountPage() {
  const router = useRouter();
  return (
    <main>
      <h1>Your account</h1>
      <AccountPanel
        onRequireAuth={() => router.replace("/login")}
        onLoggedOut={() => router.replace("/login")}
      />
    </main>
  );
}
