"use client";

/**
 * Note detail route (NF-13/14).
 *
 * Hosts one note's editor, anchored passages, and backlinks. Unauthenticated
 * visitors are redirected to `/login` — a UX convenience ONLY, NOT a security
 * boundary: FastAPI enforces authentication and ownership on every notes call
 * regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useParams, useRouter } from "next/navigation";

import { NoteDetailScreen } from "@/app/components/notes/note-detail-screen";

export default function NoteDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  return (
    <main className="flex-1 p-6">
      <NoteDetailScreen
        noteId={params.id}
        onRequireAuth={() => router.replace("/login")}
      />
    </main>
  );
}
