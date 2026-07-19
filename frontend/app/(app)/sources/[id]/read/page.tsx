"use client";

/**
 * Reader route (RD-26/27).
 *
 * A thin client wrapper around `ChapterReader`, which resolves auth and the
 * chapter in parallel and renders the chapter as one continuous article.
 * Unauthenticated visitors are redirected to `/login` — a UX convenience ONLY,
 * NOT a security boundary: FastAPI enforces authentication and ownership on every
 * `/api/sources/{id}/chapter` call regardless of client-side routing
 * (FR-AUTH-007, ADR-017). `ChapterReader` consumes `useSearchParams`, which
 * requires a `<Suspense>` boundary to satisfy the Next.js build.
 */

import { useParams, useRouter } from "next/navigation";
import { Suspense } from "react";

import { ChapterReader } from "@/app/components/chapter-reader";

export default function ReadPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main className="flex h-[calc(100vh-3rem)] flex-col overflow-y-auto p-4">
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <ChapterReader
          sourceId={params.id}
          onRequireAuth={() => router.replace("/login")}
        />
      </Suspense>
    </main>
  );
}
