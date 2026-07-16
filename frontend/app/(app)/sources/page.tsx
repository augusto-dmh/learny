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

import { SourcesPanel } from "@/app/components/SourcesPanel";

export default function SourcesPage() {
  const router = useRouter();
  return (
    <main>
      <h1>Your sources</h1>
      <SourcesPanel onRequireAuth={() => router.replace("/login")} />
    </main>
  );
}
