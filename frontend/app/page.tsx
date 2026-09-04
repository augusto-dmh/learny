import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * Public landing (RFC-004 Cycle E — HOME-20).
 *
 * A minimal, identity-styled front door for anonymous visitors: the product
 * name, a one-line value proposition, a static cited-answer proof from
 * *The Art of War*, and the two entry CTAs. It is a server component styled
 * entirely with the Iron Gall tokens (ADR-027) so it renders in both light and
 * dark without client JavaScript. No marketing sections and no generation fetch.
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
      <figure className="mx-auto max-w-lg space-y-3">
        <blockquote className="text-xl font-medium leading-relaxed text-foreground">
          All warfare is based on deception.
        </blockquote>
        <figcaption className="text-sm text-muted-foreground">
          <cite className="not-italic font-medium text-foreground">
            The Art of War
          </cite>
          <span className="mx-2" aria-hidden="true">
            ·
          </span>
          <span>I. Laying Plans</span>
        </figcaption>
      </figure>
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
