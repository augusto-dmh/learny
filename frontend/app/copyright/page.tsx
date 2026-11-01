import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { LegalParagraphs, LegalSection } from "@/app/components/legal";

/**
 * Public Copyright / notice-and-takedown page (DOOR-27, DOOR-28), in the
 * negotiated locale.
 *
 * The designated DMCA contact is read from the environment *inside the
 * component render* — not at module scope, where a build-time prerender would
 * bake the build machine's value into static HTML. The page is dynamic so the
 * operator's runtime configuration is what visitors see.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal.copyright");
  return { title: t("title") };
}

// The page must reflect the operator's runtime environment, not the build's.
export const dynamic = "force-dynamic";

export default async function CopyrightPage() {
  const t = await getTranslations("legal.copyright");
  const dmcaEmail = process.env.LEARNY_DMCA_CONTACT_EMAIL;

  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        {t("title")}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("subtitle")}</p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <LegalSection title={t("agentTitle")}>
          <p>
            {t("agentBody")}{" "}
            {dmcaEmail ? (
              <a
                href={`mailto:${dmcaEmail}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {dmcaEmail}
              </a>
            ) : (
              <span className="text-muted-foreground">{t("agentMissing")}</span>
            )}
            .
          </p>
        </LegalSection>

        <LegalSection title={t("filingTitle")}>
          <LegalParagraphs body={t("filingBody")} />
        </LegalSection>

        <LegalSection title={t("actionTitle")}>
          <LegalParagraphs body={t("actionBody")} />
        </LegalSection>

        <LegalSection title={t("uploadsTitle")}>
          <p>
            {t.rich("uploadsBody", {
              link: (chunks) => (
                <a
                  href="/terms"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {chunks}
                </a>
              ),
            })}
          </p>
        </LegalSection>
      </div>
    </main>
  );
}
