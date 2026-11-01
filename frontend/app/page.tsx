import Link from "next/link";
import { useTranslations } from "next-intl";

import { GuestSampleAsk } from "@/app/components/guest-sample-ask";
import { LocaleSwitcher } from "@/app/components/locale-switcher";
import { Button } from "@/components/ui/button";

/**
 * Public landing (RFC-004 Cycle E — HOME-20).
 *
 * A minimal, identity-styled front door for anonymous visitors: the product
 * name, a one-line value proposition, a static cited-answer proof from
 * *The Art of War*, the capped guest sample ask (the AD-320 thaw — a
 * no-account taste of the real, citation-grounded product), and the two entry
 * CTAs. The static proof stays a server render in both light and dark; the
 * sample ask is the page's one client island.
 *
 * The proof is book text, so it stays verbatim in the book's language (`lang`)
 * in every interface locale — the same rule citations follow everywhere else.
 */
const PROOF = {
  lang: "en",
  quote: "All warfare is based on deception.",
  book: "The Art of War",
  section: "I. Laying Plans",
} as const;

export default function LandingPage() {
  const t = useTranslations();
  return (
    <main className="relative flex min-h-svh flex-col items-center justify-center gap-8 bg-background px-6 py-12 text-center text-foreground">
      <LocaleSwitcher className="absolute right-4 top-4" />
      <div className="space-y-4">
        <h1 className="text-5xl font-semibold tracking-tight text-primary">
          Learny
        </h1>
        <p className="mx-auto max-w-md text-lg text-muted-foreground">
          {t("landing.tagline")}
        </p>
      </div>
      <figure className="mx-auto max-w-lg space-y-3">
        <blockquote
          lang={PROOF.lang}
          className="text-xl font-medium leading-relaxed text-foreground"
        >
          {PROOF.quote}
        </blockquote>
        <figcaption className="text-sm text-muted-foreground">
          <cite
            lang={PROOF.lang}
            className="not-italic font-medium text-foreground"
          >
            {PROOF.book}
          </cite>
          <span className="mx-2" aria-hidden="true">
            ·
          </span>
          <span lang={PROOF.lang}>{PROOF.section}</span>
        </figcaption>
      </figure>
      <GuestSampleAsk />
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild size="lg">
          <Link href="/register">{t("auth.createAccount")}</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/login">{t("auth.logIn")}</Link>
        </Button>
      </div>
    </main>
  );
}
