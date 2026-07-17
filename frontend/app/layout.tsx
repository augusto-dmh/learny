import type { CSSProperties, ReactNode } from "react";

import { GeistSans } from "geist/font/sans";

import "./globals.css";
import { ThemeProvider } from "@/app/components/theme-provider";

export const metadata = {
  title: "Learny",
  description: "Learny — book intelligence",
};

// Geist ships its variable as `--font-geist-sans`; the shadcn token stylesheet
// reads `--font-sans`, so bind the two at the root.
const fontVars = { "--font-sans": "var(--font-geist-sans)" } as CSSProperties;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={GeistSans.variable}
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
