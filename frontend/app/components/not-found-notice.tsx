/**
 * The terminal "nothing to ground an answer in" state, shown in place of
 * citations.
 *
 * There are two distinct facts here and the reader is told which one happened. A
 * whole-book conversation coming up empty means the book does not cover it. A
 * conversation scoped to a chapter coming up empty means only that *this* part
 * of the book does not cover it — the answer may sit a few chapters away, and a
 * reader who is told "not in this book" would wrongly stop looking.
 */

import { type AnswerStatus } from "@/app/lib/streaming";

/** Whether a status is one of the two not-found outcomes. */
export function isNotFound(status: AnswerStatus | null): boolean {
  return status === "not_found_in_scope" || status === "not_found_in_source";
}

export function NotFoundNotice({ status }: { status: AnswerStatus }) {
  return (
    <p data-testid="not-found" className="text-muted-foreground">
      {status === "not_found_in_scope"
        ? "That was not found in the part of the book this conversation covers. It may be answered elsewhere in the book."
        : "That was not found in this book."}
    </p>
  );
}
