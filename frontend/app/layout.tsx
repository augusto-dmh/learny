import type { ReactNode } from "react";

export const metadata = {
  title: "Learny",
  description: "Learny — book intelligence",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
