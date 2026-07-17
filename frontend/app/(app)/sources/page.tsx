"use client";

/**
 * Sources screen (T8, SRC-11).
 *
 * Lists the signed-in user's sources and uploads new EPUBs. Unauthenticated
 * visitors are redirected to `/login` — a UX convenience ONLY, NOT a security
 * boundary: the data comes from FastAPI, which enforces authentication and
 * per-user ownership on every `/api/sources*` call regardless of client-side
 * routing (FR-AUTH-007, ADR-017).
 */

import { useRouter } from "next/navigation";

import { LibraryScreen } from "@/app/components/library-screen";

export default function SourcesPage() {
  const router = useRouter();
  return (
    <main className="flex-1 p-6">
      <h1 className="mb-6 text-2xl font-semibold">Your library</h1>
      <LibraryScreen onRequireAuth={() => router.replace("/login")} />
    </main>
  );
}
