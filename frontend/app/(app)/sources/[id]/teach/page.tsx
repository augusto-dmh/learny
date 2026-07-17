"use client";

/**
 * Teach screen route (FE-11..FE-13).
 *
 * Hosts the streaming teach surface for one source. Unauthenticated visitors are
 * redirected to `/login` — a UX convenience ONLY, NOT a security boundary:
 * FastAPI enforces authentication, ownership, readiness, and target scoping on
 * every teaching call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useParams, useRouter } from "next/navigation";

import { TeachScreen } from "@/app/components/teach-screen";

export default function TeachPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main className="flex h-[calc(100vh-3rem)] flex-col p-4">
      <h1 className="mb-4 text-lg font-semibold">Teach</h1>
      <TeachScreen
        sourceId={params.id}
        onRequireAuth={() => router.replace("/login")}
      />
    </main>
  );
}
