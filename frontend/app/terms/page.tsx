import type { Metadata } from "next";
import Link from "next/link";

/**
 * Public Terms of Service (DOOR-27).
 *
 * A signed-out server page with short, honest copy committed here rather than
 * generated per request: a policy that shifts under the reader is worse than a
 * short one. Styling follows the public landing page (Iron Gall tokens, no
 * client JavaScript).
 */
export const metadata: Metadata = { title: "Terms of Service" };

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        Terms of Service
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        These terms govern your use of Learny. By creating an account you agree
        to them.
      </p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">Your account</h2>
          <p>
            You need an account to store books and study. Keep your credentials
            private; you are responsible for activity under your account. Some
            instances are invite-only: an invitation is a revocable permission,
            not an entitlement.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Uploads and copyright</h2>
          <p>
            You may upload books you have the right to use privately. You keep
            your rights; Learny does not grant you any additional copyright. You
            warrant that your uploads do not infringe others&apos; rights.
            Learny will not publish, sell, or share your files, and will disable
            access to material identified in a valid copyright notice (see{" "}
            <Link href="/copyright" className="text-primary underline-offset-4 hover:underline">
              Copyright / DMCA
            </Link>
            ). Accounts that repeatedly infringe may be terminated.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Acceptable use</h2>
          <p>
            Do not abuse the service: no attacking other users or the
            infrastructure, no scraping, no reselling access, and no presenting
            generated output as the book itself. Rate and storage limits apply.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">AI answers</h2>
          <p>
            Answers are generated and can be wrong, incomplete, or misleading —
            even when they cite a passage. Check the citation before relying on
            an answer. Learny provides study tooling, not professional advice.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Termination and deletion</h2>
          <p>
            You can delete your account at any time; deleting removes your
            stored files and account data. We may suspend or terminate accounts
            that violate these terms, including for repeated copyright
            infringement.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Disclaimers and liability</h2>
          <p>
            The service is provided &ldquo;as is&rdquo; without warranties of
            any kind. To the extent permitted by law, Learny is not liable for
            indirect or consequential damages arising from your use of the
            service.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Governing law</h2>
          <p>
            These terms are governed by the laws of the Federative Republic of
            Brazil. See our{" "}
            <Link href="/privacy" className="text-primary underline-offset-4 hover:underline">
              Privacy Policy
            </Link>{" "}
            for how your data is handled.
          </p>
        </section>
      </div>
    </main>
  );
}
