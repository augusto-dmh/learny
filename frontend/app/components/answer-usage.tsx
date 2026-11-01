"use client";

/**
 * The per-answer usage line (S4): what one answer's provider call consumed,
 * rendered under the answer in the Chat surface.
 *
 * The line renders only when the adapter reported usage — the backend emits
 * its `data-answer-usage` part (and the restored turn carries the usage
 * fields) only then, so an absent report renders nothing at all, not a zero.
 * The token counts ride every reported answer; the estimated cost appears only
 * when the learner's own key paid the call, labeled as such, because a
 * house-served answer costs the learner nothing and pricing it would imply
 * they were billed.
 */

import { useLocale, useTranslations } from "next-intl";

import { type AnswerUsage } from "@/app/lib/streaming";

import { formatUsdMicros } from "@/app/lib/money";

export function AnswerUsageLine({ usage }: { usage: AnswerUsage }) {
  const t = useTranslations("chat.usage");
  const locale = useLocale();
  return (
    <p className="text-xs text-muted-foreground" data-testid="answer-usage">
      {t("tokens", { input: usage.input_tokens, output: usage.output_tokens })}
      {usage.user_keyed && usage.cost_usd_micros !== null
        ? ` · ${t("ownKey", { cost: formatUsdMicros(usage.cost_usd_micros, locale) })}`
        : null}
    </p>
  );
}
