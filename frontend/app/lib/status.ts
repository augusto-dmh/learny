/**
 * Shared status→badge mapping for a source's projected ingestion status, used by
 * both the library screen and the sidebar so the status contract lives once.
 */

/** Map a source's projected status to a badge variant. */
export function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "ready":
      return "default";
    case "processing":
      return "secondary";
    case "failed":
      return "destructive";
    default:
      return "outline";
  }
}
