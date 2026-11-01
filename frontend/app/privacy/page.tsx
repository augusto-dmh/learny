import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { LegalParagraphs, LegalSection } from "@/app/components/legal";

/**
 * Public Privacy Policy (DOOR-27, DOOR-29), in the negotiated locale.
 *
 * Names the AI subprocessors on the live path (OpenAI for embeddings,
 * Anthropic for generation) and makes no zero-data-retention claim. The
 * adult-only posture and the LGPD data-subject rights (art. 18) are stated
 * here in full, including the international-transfer note and the ANPD
 * complaint route — content-bearing copy that lives in the catalogs, not in
 * this file.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal.privacy");
  return { title: t("title") };
}

export default async function PrivacyPage() {
  const t = await getTranslations("legal.privacy");
  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        {t("title")}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("subtitle")}</p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <LegalSection title={t("dataTitle")}>
          <LegalParagraphs body={t("dataBody")} />
        </LegalSection>

        <LegalSection title={t("whyTitle")}>
          <LegalParagraphs body={t("whyBody")} />
        </LegalSection>

        <LegalSection title={t("subprocessorsTitle")}>
          <LegalParagraphs body={t("subprocessorsBody")} />
        </LegalSection>

        <LegalSection title={t("transfersTitle")}>
          <LegalParagraphs body={t("transfersBody")} />
        </LegalSection>

        <LegalSection title={t("retentionTitle")}>
          <LegalParagraphs body={t("retentionBody")} />
        </LegalSection>

        <LegalSection title={t("sharingTitle")}>
          <LegalParagraphs body={t("sharingBody")} />
        </LegalSection>

        <LegalSection title={t("rightsTitle")}>
          <LegalParagraphs body={`${t("rightsIntro")}\n\n${t("rightsList")}`} />
          <p>
            {t.rich("rightsContact", {
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
          <LegalParagraphs body={t("anpdBody")} />
        </LegalSection>

        <LegalSection title={t("securityTitle")}>
          <LegalParagraphs body={t("securityBody")} />
        </LegalSection>
      </div>
    </main>
  );
}
