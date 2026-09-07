import type { Metadata } from "next";

/**
 * Public Copyright / notice-and-takedown page (DOOR-27, DOOR-28).
 *
 * The designated DMCA contact is read from the environment *inside the
 * component render* — not at module scope, where a build-time prerender would
 * bake the build machine's value into static HTML. The page is dynamic so the
 * operator's runtime configuration is what visitors see.
 */
export const metadata: Metadata = { title: "Copyright / DMCA" };

// The page must reflect the operator's runtime environment, not the build's.
export const dynamic = "force-dynamic";

export default function CopyrightPage() {
  const dmcaEmail = process.env.LEARNY_DMCA_CONTACT_EMAIL;

  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold tracking-tight text-primary">
        Copyright / DMCA
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        How to report copyright infringement on this instance.
      </p>

      <div className="prose-reading mt-8 space-y-6 text-base leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">Designated agent</h2>
          <p>
            Copyright notices for this instance are handled by its designated
            agent. Send notices to{" "}
            {dmcaEmail ? (
              <a
                href={`mailto:${dmcaEmail}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {dmcaEmail}
              </a>
            ) : (
              <span className="text-muted-foreground">
                (agent mailbox not configured)
              </span>
            )}
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Filing a notice</h2>
          <p>
            If you believe material on this instance infringes your copyright,
            send the agent a notice that includes: identification of the
            copyrighted work; identification of the infringing material (the
            account or content involved) and enough detail for us to locate it;
            your contact information; a statement of your good-faith belief that
            the use is unauthorized; a statement, under penalty of perjury, that
            the information in your notice is accurate and that you are the
            rights holder or authorized to act for them; and your signature.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">What we do</h2>
          <p>
            For a valid notice we remove or disable access to the identified
            material and may notify the uploader. Repeat infringers lose their
            accounts. If your material was removed by mistake or
            misidentification, you may send a counter-notice to the same
            address with the removed material&apos;s identification, your contact
            information, and a statement under penalty of perjury that the
            removal resulted from mistake or misidentification.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">Uploads</h2>
          <p>
            Learny stores private study copies. Uploaders warrant they have the
            right to use the works they upload; see the{" "}
            <a href="/terms" className="text-primary underline-offset-4 hover:underline">
              Terms of Service
            </a>
            . This page is not legal advice and does not limit any rights you
            have under applicable law.
          </p>
        </section>
      </div>
    </main>
  );
}
