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
 * four decimal places: `10500` micros reads as US$0.0105. Under 100 micros
 * four decimals would round a cost that was paid down to zero, so those
 * amounts carry an explicit floor instead: `49` micros reads as `<US$0,0001`
 * in pt-BR — never as $0.
 */

const MICROS_PER_USD = 1_000_000;

/** Micros under this render as $0 at four decimals, so they take the floor. */
const FLOOR_MICROS = 100;

function formatUsd(amount: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(amount);
}

export function formatUsdMicros(micros: number, locale: string): string {
  if (micros > 0 && micros < FLOOR_MICROS) {
    return `<${formatUsd(FLOOR_MICROS / MICROS_PER_USD, locale)}`;
  }
  return formatUsd(micros / MICROS_PER_USD, locale);
}
