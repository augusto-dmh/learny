/**
 * The ink-line signature rule (ADR-027): a token-only hairline — `--border`
 * rail, `--primary` ink — shared by every surface that wears the signature.
 * The fill is functional, never decorative: pass `percent` only where the line
 * encodes real reading progress; omit it for the static header rule.
 */
export function InkLine({ percent }: { percent?: number }) {
  return (
    <div data-testid="ink-line" aria-hidden className="h-px w-full bg-border">
      {percent === undefined ? null : (
        <div
          data-testid="ink-line-fill"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
          className="h-full bg-primary transition-[width] duration-300 motion-reduce:transition-none"
        />
      )}
    </div>
  );
}
