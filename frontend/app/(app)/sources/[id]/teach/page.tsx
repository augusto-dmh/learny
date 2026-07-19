/**
 * Teach route tombstone (RA-04).
 *
 * Teach is now a mode of the reader side panel, not a standalone screen. This
 * route survives only to redirect any lingering link or bookmark into the reader
 * with the Teach panel open. FastAPI still enforces auth, ownership, readiness,
 * and target scoping on every teaching call regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import { redirect } from "next/navigation";

export default async function TeachPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/sources/${id}/read?panel=teach`);
}
