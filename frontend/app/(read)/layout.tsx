import type { ReactNode } from "react";

/**
 * Immersive reading shell (READ-16): `/sources/{id}/read` is outside `(app)`,
 * so `AppSidebar` and `AuthHeader` are absent from the document. Auth still
 * comes from the root layout / session cookies.
 */
export default function ReadLayout({ children }: { children: ReactNode }) {
  return children;
}
