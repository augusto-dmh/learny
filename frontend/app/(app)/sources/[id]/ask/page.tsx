/**
 * Ask route tombstone (RA-04).
 *
 * Ask is now a mode of the reader side panel, not a standalone screen. This route
 * survives only to redirect any lingering link or bookmark into the reader with
 * the Ask panel open. FastAPI still enforces auth, ownership, and readiness on
 * every question call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { redirect } from "next/navigation";

export default async function AskPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/sources/${id}/read?panel=ask`);
}
