import type { AppLocale } from "./i18n/config";
import type en from "./messages/en.json";

// Typed message keys: `en.json` is the source of truth, so a key used in code
// and absent from it fails `tsc --noEmit` (the pt-BR catalog is held to the same
// key set by `tests/i18n-parity.test.ts`).
declare module "next-intl" {
  interface AppConfig {
    Locale: AppLocale;
    Messages: typeof en;
  }
}
