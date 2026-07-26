"use client";

/**
 * The notes-scope control for the Ask and Teach panels (NL-04).
 *
 * The control does not change *how* an answer is written — it changes what the
 * answer is allowed to be grounded in, by adding the reader's own notes to the
 * book. It says so, because a reader who reads it as a formatting preference has
 * no way to explain why the same question answers differently with it on.
 *
 * Purely presentational: it reflects `checked` and reports a flip via `onChange`.
 * The panel owns the preference (`use-include-notes`) and hands the choice to the
 * conversation it creates.
 *
 * The choice belongs to the conversation, so once one exists the control is
 * `locked`: it reports what that thread was started with and says so, rather
 * than staying flippable and quietly changing nothing.
 */

import { useId } from "react";

export function IncludeNotesToggle({
  checked,
  onChange,
  locked = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  /** A conversation already fixed this choice, making the control read-only. */
  locked?: boolean;
}) {
  const descriptionId = useId();
  return (
    <div className="space-y-1">
      <label className="flex w-fit items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={checked}
          disabled={locked}
          aria-describedby={descriptionId}
          onChange={(event) => onChange(event.target.checked)}
          className="size-3.5 accent-primary disabled:opacity-60"
        />
        Search my notes too
      </label>
      <p id={descriptionId} className="text-xs text-muted-foreground">
        Your own notes on this book are searched alongside the book itself, so
        answers can be grounded in what you have written.
        {locked
          ? " This conversation was started with this choice — start a new one to change it."
          : null}
      </p>
    </div>
  );
}
