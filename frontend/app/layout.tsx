import type { ReactNode } from "react";

import "./globals.css";

export const metadata = {
  title: "Learny",
  description: "Learny — book intelligence",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
