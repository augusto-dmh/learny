"use client";

/**
 * The `Aa` reading-controls popover (RD-17/19/20/21).
 *
 * A controlled surface over the four reader axes: type size and line spacing
 * (device-local, from `useReadingSettings`), appearance (Default / Paper), and
 * theme (Light / Dark / System via next-themes). Size, spacing, and appearance
 * are owned by the parent so one settings instance drives both the popover and
 * the reader container; theme is owned by next-themes here.
 *
 * The appearance axis is always shown, never hidden: under a dark theme the Paper
 * choice is inert (ADR-027 keeps dark on the Iron Gall night palette via the
 * guarded `[data-appearance="paper"]` selector), so the popover communicates that
 * with a note rather than removing the control (RD-20).
 */

import { useFormatter, useTranslations } from "next-intl";
import { useTheme } from "next-themes";

import {
  READING_LEADINGS,
  READING_SIZES,
  type ReadingAppearance,
  type ReadingLeading,
  type ReadingSize,
} from "@/app/components/use-reading-settings";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const APPEARANCES: readonly ReadingAppearance[] = ["default", "paper"];

const THEMES = ["light", "dark", "system"] as const;

/** One selectable step in a segmented control; `selected` shows the pressed state. */
function Segment({
  selected,
  onClick,
  className,
  children,
  ...props
}: React.ComponentProps<"button"> & { selected: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "flex-1 rounded-md border px-2 py-1 text-sm transition-colors",
        selected
          ? "border-primary bg-accent text-accent-foreground"
          : "border-border text-muted-foreground hover:bg-accent/50",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** A labelled row of segmented steps. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex gap-1.5">{children}</div>
    </div>
  );
}

export function ReadingControls({
  size,
  leading,
  appearance,
  onSizeChange,
  onLeadingChange,
  onAppearanceChange,
}: {
  size: ReadingSize;
  leading: ReadingLeading;
  appearance: ReadingAppearance;
  onSizeChange: (size: ReadingSize) => void;
  onLeadingChange: (leading: ReadingLeading) => void;
  onAppearanceChange: (appearance: ReadingAppearance) => void;
}) {
  const t = useTranslations("reader.controls");
  const format = useFormatter();
  const { theme, resolvedTheme, setTheme } = useTheme();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={t("label")}
          className="font-serif"
        >
          Aa
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 gap-3.5">
        <Field label={t("typeSize")}>
          {READING_SIZES.map((step) => (
            <Segment
              key={step}
              selected={step === size}
              onClick={() => onSizeChange(step)}
              aria-label={t("typeSizeStep", { size: step })}
            >
              <span style={{ fontSize: `${step}px` }}>A</span>
            </Segment>
          ))}
        </Field>

        <Field label={t("lineSpacing")}>
          {READING_LEADINGS.map((step) => (
            <Segment
              key={step}
              selected={step === leading}
              onClick={() => onLeadingChange(step)}
              aria-label={t("lineSpacingStep", { step })}
            >
              {format.number(step, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              })}
            </Segment>
          ))}
        </Field>

        <Field label={t("appearance")}>
          {APPEARANCES.map((value) => (
            <Segment
              key={value}
              selected={value === appearance}
              onClick={() => onAppearanceChange(value)}
            >
              {t(`appearances.${value}`)}
            </Segment>
          ))}
        </Field>
        {resolvedTheme === "dark" ? (
          <p className="text-xs text-muted-foreground">
            {t("darkNote")}
          </p>
        ) : null}

        <Field label={t("theme")}>
          {THEMES.map((value) => (
            <Segment
              key={value}
              selected={value === theme}
              onClick={() => setTheme(value)}
            >
              {t(`themes.${value}`)}
            </Segment>
          ))}
        </Field>
      </PopoverContent>
    </Popover>
  );
}
