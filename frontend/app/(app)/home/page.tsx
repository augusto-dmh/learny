/**
 * Home route (RFC-004 Cycle E — HOME-17).
 *
 * The signed-in landing surface: a two-card Home (continue-reading hero + due
 * reviews) that post-login/post-register redirects land on (AD-150). The page is
 * a thin shell; `HomeScreen` owns the client-side fetches and their independent
 * card states.
 */

import { HomeScreen } from "@/app/components/home-screen";
import { InkLine } from "@/app/components/ink-line";

export default function HomePage() {
  return (
    <main className="flex-1 p-6">
      <header className="mb-6 space-y-2">
        <h1 className="text-2xl font-semibold">Home</h1>
        <InkLine />
      </header>
      <HomeScreen />
    </main>
  );
}
