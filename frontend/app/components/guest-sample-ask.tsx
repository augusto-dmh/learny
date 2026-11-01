"use client";

/**
 * The landing page's capped guest sample ask (AD-320 thaw).
 *
 * A stranger's taste of the product: one question about the shared sample,
 * answered with the same cited-answer rendering an authenticated Ask uses
 * (`CitedAnswer`), always labeled as the shared sample. The caps live on the
 * backend (per-IP rate limit + the sample's own daily budget), and every
 * refusal has honest catalog copy — the exhausted budget says so instead of
 * quietly degrading, because a fake answer is worse than no answer.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";

import { CitedAnswer } from "@/app/components/cited-answer";
import { useErrorMessage } from "@/app/components/use-error-message";
import { askSample, type SampleAskResult } from "@/app/lib/sample-ask";
import { ApiError } from "@/app/lib/errors";
import { Button } from "@/components/ui/button";

export function GuestSampleAsk() {
  const t = useTranslations("landing.sampleAsk");
  const errorMessage = useErrorMessage();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SampleAskResult | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setNotice(null);
    setPending(true);
    try {
      setResult(await askSample(question.trim()));
    } catch (err) {
      setResult(null);
      // The exhausted cap gets its own honest line — the visitor did nothing
      // wrong and a generic failure would hide the way back in.
      setNotice(
        err instanceof ApiError && err.status === 429
          ? t("exhausted")
          : errorMessage(err, "sampleAsk"),
      );
    } finally {
      setPending(false);
    }
  }

  const firstSourceId = result?.citations[0]?.source_id ?? "";

  return (
    <section
      aria-label={t("label")}
      className="mx-auto w-full max-w-lg rounded-lg border bg-card p-5 text-left"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("label")}</h2>
        <span className="text-xs text-muted-foreground">{t("capNote")}</span>
      </div>
      <form onSubmit={handleSubmit} className="mt-3 space-y-3" aria-label={t("formLabel")}>
        <textarea
          data-testid="guest-ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t("suggestedQuestion")}
          rows={2}
          maxLength={400}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" disabled={pending || question.trim().length === 0} className="w-full">
          {pending ? t("working") : t("ask")}
        </Button>
      </form>
      {notice ? (
        <p role="alert" data-testid="guest-ask-error" className="mt-3 text-sm text-destructive">
          {notice}
        </p>
      ) : null}
      {result ? (
        result.found ? (
          <div data-testid="guest-ask-answer" className="mt-4">
            <CitedAnswer sourceId={firstSourceId} text={result.answer ?? ""} citations={result.citations} />
          </div>
        ) : (
          <p data-testid="guest-ask-not-found" className="mt-4 text-sm text-muted-foreground">
            {t("notFound")}
          </p>
        )
      ) : null}
    </section>
  );
}
