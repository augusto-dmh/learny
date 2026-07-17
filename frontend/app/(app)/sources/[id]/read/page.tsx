"use client";

/**
 * Reader route (FE-15/FE-17).
 *
 * A thin client wrapper around `SectionReader`. Unauthenticated visitors are
 * redirected to `/login` — a UX convenience ONLY, NOT a security boundary:
 * FastAPI enforces authentication and ownership on every
 * `/api/sources/{id}/section` call regardless of client-side routing
 * (FR-AUTH-007, ADR-017). `SectionReader` consumes `useSearchParams`, which
 * requires a `<Suspense>` boundary to satisfy the Next.js build.
 */

import { useParams, useRouter } from "next/navigation";
import { Suspense } from "react";

import { SectionReader } from "@/app/components/section-reader";

export default function ReadPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main className="flex h-[calc(100vh-3rem)] flex-col overflow-y-auto p-4">
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <SectionReader
          sourceId={params.id}
          onRequireAuth={() => router.replace("/login")}
        />
      </Suspense>
    </main>
  );
}
