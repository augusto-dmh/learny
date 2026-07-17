"use client";

/**
 * Review route (QUIZ-19).
 *
 * Hosts the spaced-repetition due queue. An optional `?source_id=` narrows the
 * session to one book (the library's per-source "Review" link); with no param it
 * reviews everything due across the user's sources. Unauthenticated visitors are
 * redirected to `/login` — a UX convenience ONLY, NOT a security boundary:
 * FastAPI enforces authentication and ownership on every review call regardless
 * of client-side routing (FR-AUTH-007, ADR-017). `ReviewSession` reads
 * `useSearchParams`, which requires a `<Suspense>` boundary for the Next.js build.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ReviewScreen } from "@/app/components/review-screen";

function ReviewSession() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sourceId = searchParams.get("source_id") ?? undefined;
  return (
    <ReviewScreen
      sourceId={sourceId}
      onRequireAuth={() => router.replace("/login")}
    />
  );
}

export default function ReviewPage() {
  return (
    <main className="flex-1 p-6">
      <h1 className="mb-6 text-2xl font-semibold">Review</h1>
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <ReviewSession />
      </Suspense>
    </main>
  );
}
