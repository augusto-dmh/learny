import type { Metadata } from "next";
import Link from "next/link";

/**
 * Public Privacy Policy (DOOR-27, DOOR-29).
 *
 * Names the AI subprocessors on the live path (OpenAI for embeddings,
 * Anthropic for generation) and makes no zero-data-retention claim: both
 * providers retain API traffic for a limited period for abuse monitoring, and
 * the exact windows are their published policies — this page never states a
 * number this product does not control.
 */
export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        Privacy Policy
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        What Learny collects, why, and what happens to it.
      </p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">Data we hold</h2>
          <p>
            Your account email and a password hash (never the password itself);
            your uploaded books and the text, embeddings, and study materials
            derived from them; your conversations, quizzes, notes, highlights,
            and reading progress; and session cookies that keep you signed in.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Why we hold it</h2>
          <p>
            To operate your library and study features (to perform the service
            you signed up for), to keep the service secure (rate limiting and
            abuse prevention), and to answer support and legal requests.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">AI subprocessors</h2>
          <p>
            Two AI providers process content on the live path.{" "}
            <strong>OpenAI</strong> receives short text chunks to compute
            embeddings; <strong>Anthropic</strong> receives retrieved passages
            and your questions to generate answers. Neither provider is
            authorized to use this traffic to train its models, but both retain
            it for a limited period of their own abuse monitoring — we make no
            zero-retention claim on their behalf. Book text is sent only as far
            as retrieval requires, and prompt bodies are kept out of Learny&apos;s
            own logs.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Retention and deletion</h2>
          <p>
            We keep the data above while your account is active. When you delete
            your account, your stored files and account data are removed.
            Backups expire on their own schedule.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Sharing</h2>
          <p>
            We do not sell your data and do not share your books, notes, or
            conversations publicly. Beyond the AI subprocessors named above and
            the hosting and storage providers that run the service, data leaves
            Learny only when the law requires it.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Your rights</h2>
          <p>
            You can access, correct, export, and delete your data — library
            export and full account deletion are built into the product. For
            anything else, contact the operator through the address on the{" "}
            <Link href="/copyright" className="text-primary underline-offset-4 hover:underline">
              copyright page
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Security and children</h2>
          <p>
            Sessions are HTTP-only cookies; passwords are hashed; traffic is
            encrypted in transit. Learny is not directed at children under 13,
            and we do not knowingly create accounts for them.
          </p>
        </section>
      </div>
    </main>
  );
}
