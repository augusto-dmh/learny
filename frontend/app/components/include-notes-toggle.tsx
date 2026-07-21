"use client";

/**
 * "Include my notes" toggle for the Ask and Teach panels (NL-04).
 *
 * A plain, accessible checkbox (native input inside its label) that lets the
 * reader fold their own notes into an answer's evidence. The panel owns the
 * preference (`use-include-notes`) and whether the flag is sent; this component is
 * purely presentational — it reflects `checked` and reports a flip via `onChange`.
 */

export function IncludeNotesToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex w-fit items-center gap-2 text-xs text-muted-foreground">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-3.5 accent-primary"
      />
      Include my notes
    </label>
  );
}
