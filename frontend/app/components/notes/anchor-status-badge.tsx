/**
 * Anchor-status badge (NF-13/14) — one badge for a note anchor's reconcile status.
 *
 * Shared by the notes list and the note detail so the orphaned state reads the
 * same everywhere: an orphaned anchor (its passage gone after a re-ingest) gets a
 * distinct destructive treatment and is never hidden, while active/stale anchors
 * render as quiet outline badges. An unrecognized status still renders its own
 * label rather than vanishing.
 */

import { Badge } from "@/components/ui/badge";

export function AnchorStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant={status === "orphaned" ? "destructive" : "outline"}
      data-testid={`anchor-status-${status}`}
    >
      {status}
    </Badge>
  );
}
