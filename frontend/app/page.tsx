import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * Public landing (RFC-004 Cycle E — HOME-20).
 *
 * A minimal, identity-styled front door for anonymous visitors: the product
 * name, a one-line value proposition, and the two entry CTAs. It is a server
 * component styled entirely with the Iron Gall tokens (ADR-027) so it renders in
 * both light and dark without client JavaScript. No marketing sections.
 */
export default function LandingPage() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-8 bg-background px-6 text-center text-foreground">
      <div className="space-y-4">
        <h1 className="text-5xl font-semibold tracking-tight text-primary">
          Learny
        </h1>
        <p className="mx-auto max-w-md text-lg text-muted-foreground">
          Turn your books into cited answers and lasting recall.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild size="lg">
          <Link href="/register">Create account</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/login">Log in</Link>
        </Button>
      </div>
    </main>
  );
}
