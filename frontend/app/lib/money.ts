/**
 * The one formatter for the learner-facing money Learny estimates: the
 * per-answer cost on a learner-keyed answer and the keys section's
 * month-to-date line and budget. Everything the learner is told about their
 * own spend is USD (the provider catalogs are priced in USD; the budget is
 * denominated in USD on the wire as micros), so the currency is fixed here and
 * only the locale varies — symbol, grouping and decimal separator follow the
 * interface language.
 *
 * Provider answers are routinely below one cent, so the format keeps up to
 * four decimal places: `10500` micros reads as US$0.0105. Trailing zeros are
 * dropped, so a whole-dollar budget reads as US$5.
 */

const MICROS_PER_USD = 1_000_000;

export function formatUsdMicros(micros: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(micros / MICROS_PER_USD);
}
