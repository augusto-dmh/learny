import type { ReactNode } from "react";

import { LocaleSwitcher } from "@/app/components/locale-switcher";

/**
 * Sign-in shell. Anonymous visitors have no account to store a language on, so
 * the switcher here (and on the landing page) sets the cookie alone.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh items-center justify-center p-6">
      <LocaleSwitcher className="absolute right-4 top-4" />
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
