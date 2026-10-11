"use client";

/**
 * Turn a caught request failure into the sentence the learner reads.
 *
 * Returns a function rather than a string so one call covers every catch site
 * in a component. An `ApiError` reads as its status class or its operation's
 * copy (see `errorMessageKey`); any other value reads as `fallback`. The
 * backend's `detail` is never shown.
 *
 * The returned function is rebuilt on every render, so it must not sit in the
 * dependency array of an effect that fetches: call it inside the effect's
 * callbacks instead.
 */
import { useTranslations } from "next-intl";

import { errorMessageKey, type ErrorFallback } from "@/app/lib/errors";

export type ErrorMessage = (error: unknown, fallback: ErrorFallback) => string;

export function useErrorMessage(): ErrorMessage {
  const t = useTranslations("errors");
  return (error, fallback) => t(errorMessageKey(error, fallback));
}
