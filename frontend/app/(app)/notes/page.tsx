"use client";

/**
 * Notes route (NF-13).
 *
 * Hosts the notes list. Unauthenticated visitors are redirected to `/login` — a
 * UX convenience ONLY, NOT a security boundary: FastAPI enforces authentication
 * and ownership on every notes call regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { InkLine } from "@/app/components/ink-line";
import { NotesScreen } from "@/app/components/notes/notes-screen";

export default function NotesPage() {
  const router = useRouter();
  const t = useTranslations("notes");
  return (
    <main className="flex-1 p-6">
      <header className="mb-6 space-y-2">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <InkLine />
      </header>
      <NotesScreen onRequireAuth={() => router.replace("/login")} />
    </main>
  );
}
