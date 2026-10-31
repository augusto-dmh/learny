import type { CSSProperties, ReactNode } from "react";

import { GeistSans } from "geist/font/sans";
import { Source_Serif_4 } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";

import "./globals.css";
import { ThemeProvider } from "@/app/components/theme-provider";
import { ServiceWorkerRegistrar } from "@/app/components/service-worker-registrar";

export async function generateMetadata() {
  const t = await getTranslations("meta");
  return {
    title: t("title"),
    description: t("description"),
    // The installable row: the web app manifest served by `app/manifest.ts`.
    manifest: "/manifest.webmanifest",
  };
}

// The reading serif (ADR-027): self-hosted at build time by next/font — no
// runtime font requests leave the app. latin covers Portuguese diacritics;
// latin-ext is included for full coverage of accented corpus text.
const sourceSerif = Source_Serif_4({
  subsets: ["latin", "latin-ext"],
  variable: "--font-source-serif",
});

// Geist ships its variable as `--font-geist-sans`; the shadcn token stylesheet
// reads `--font-sans`, so bind the two at the root. The serif binds the same
// way for the reader's `.prose-reading` surface.
const fontVars = {
  "--font-sans": "var(--font-geist-sans)",
  "--font-serif": "var(--font-source-serif)",
} as CSSProperties;

export default async function RootLayout({ children }: { children: ReactNode }) {
  // The locale comes from `i18n/request.ts` (cookie → Accept-Language → en); the
  // active catalog reaches client components through the provider.
  const locale = await getLocale();
  const messages = await getMessages();
  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${GeistSans.variable} ${sourceSerif.variable}`}
      style={fontVars}
    >
      <body className="antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            {children}
          </ThemeProvider>
          <ServiceWorkerRegistrar />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
