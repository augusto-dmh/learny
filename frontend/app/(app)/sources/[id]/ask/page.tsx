"use client";

/**
 * Ask screen (D2, QA-18).
 *
 * Hosts the ask panel for one source. Unauthenticated visitors are redirected
 * to `/login` — a UX convenience ONLY, NOT a security boundary: FastAPI enforces
 * authentication, ownership, and readiness on every
 * `/api/sources/{id}/questions` call regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import { useParams, useRouter } from "next/navigation";

import { AskPanel } from "@/app/components/AskPanel";

export default function AskPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main>
      <h1>Ask a question</h1>
      <AskPanel
        sourceId={params.id}
        onRequireAuth={() => router.replace("/login")}
      />
    </main>
  );
}
