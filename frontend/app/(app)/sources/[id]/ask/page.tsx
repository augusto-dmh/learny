"use client";

/**
 * Ask screen route (FE-06..FE-10).
 *
 * Hosts the streaming ask surface for one source. Unauthenticated visitors are
 * redirected to `/login` — a UX convenience ONLY, NOT a security boundary:
 * FastAPI enforces authentication, ownership, and readiness on every
 * `/api/sources/{id}/questions/stream` call regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import { useParams, useRouter } from "next/navigation";

import { AskScreen } from "@/app/components/ask-screen";

export default function AskPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main className="flex h-[calc(100vh-3rem)] flex-col p-4">
      <h1 className="mb-4 text-lg font-semibold">Ask a question</h1>
      <AskScreen
        sourceId={params.id}
        onRequireAuth={() => router.replace("/login")}
      />
    </main>
  );
}
