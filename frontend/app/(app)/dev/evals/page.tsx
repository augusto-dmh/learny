/**
 * The eval-results dashboard route (EVDASH-06).
 *
 * Deliberately unlinked: no nav entry and no reference from any student-facing
 * surface, so the reading experience is unchanged by its existence and the route
 * is reached by URL only. The backend decides whether it resolves at all — the
 * endpoint is absent from a production process and from any process that has not
 * enabled it, and the component settles to an explanatory state when it 404s.
 */

import { EvalDashboard } from "@/app/components/eval-dashboard";
import { InkLine } from "@/app/components/ink-line";

export default function EvalDashboardPage() {
  return (
    <main className="flex-1 p-6">
      <header className="mb-6 space-y-2">
        <h1 className="text-2xl font-semibold">Eval results</h1>
        <InkLine />
      </header>
      <EvalDashboard />
    </main>
  );
}
