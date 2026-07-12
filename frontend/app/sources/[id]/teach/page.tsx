"use client";

/**
 * Teach screen (E2, TEACH-22).
 *
 * Hosts the teach panel for one source. Unauthenticated visitors are redirected
 * to `/login` — a UX convenience ONLY, NOT a security boundary: FastAPI enforces
 * authentication, ownership, readiness, and target scoping on every teaching
 * call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useParams, useRouter } from "next/navigation";

import { TeachPanel } from "@/app/components/TeachPanel";

export default function TeachPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main>
      <h1>Teach</h1>
      <TeachPanel
        sourceId={params.id}
        onRequireAuth={() => router.replace("/login")}
      />
    </main>
  );
}
