import type { CSSProperties, ReactNode } from "react";

import { GeistSans } from "geist/font/sans";
import { Source_Serif_4 } from "next/font/google";

import "./globals.css";
import { ThemeProvider } from "@/app/components/theme-provider";

export const metadata = {
  title: "Learny",
  description: "Learny — book intelligence",
};

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

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${sourceSerif.variable}`}
      style={fontVars}
    >
      <body className="antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
