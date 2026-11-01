import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { LegalParagraphs, LegalSection } from "@/app/components/legal";

/**
 * Public Terms of Service (DOOR-27), in the negotiated locale.
 *
 * A signed-out server page with short, honest copy committed to the catalogs
 * rather than generated per request: a policy that shifts under the reader is
 * worse than a short one. The 18-or-older requirement is stated here — the
 * register form attests it, and the backend enforces the attestation.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal.terms");
  return { title: t("title") };
}

export default async function TermsPage() {
  const t = await getTranslations("legal.terms");
  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        {t("title")}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("subtitle")}</p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <LegalSection title={t("accountTitle")}>
          <LegalParagraphs body={t("accountBody")} />
        </LegalSection>

        <LegalSection title={t("uploadsTitle")}>
          <p>
            {t.rich("uploadsBody", {
              link: (chunks) => (
                <Link
                  href="/copyright"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </LegalSection>

        <LegalSection title={t("useTitle")}>
          <LegalParagraphs body={t("useBody")} />
        </LegalSection>

        <LegalSection title={t("aiTitle")}>
          <LegalParagraphs body={t("aiBody")} />
        </LegalSection>

        <LegalSection title={t("terminationTitle")}>
          <LegalParagraphs body={t("terminationBody")} />
        </LegalSection>

        <LegalSection title={t("disclaimersTitle")}>
          <LegalParagraphs body={t("disclaimersBody")} />
        </LegalSection>

        <LegalSection title={t("lawTitle")}>
          <p>
            {t.rich("lawBody", {
              link: (chunks) => (
                <Link
                  href="/privacy"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </LegalSection>
      </div>
    </main>
  );
}
