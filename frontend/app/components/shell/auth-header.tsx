"use client";

/**
 * App shell header (FE-02/FE-03/FE-05).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy) to show the
 * signed-in user's email, an account link, a logout control, and a light/dark
 * theme toggle. Logout carries the session-bound CSRF token (AD-007) and, like a
 * 401 from `/me`, redirects to `/login`. That redirect is a UX convenience ONLY,
 * NOT the security boundary — FastAPI enforces auth on every protected endpoint
 * regardless of client-side routing (FR-AUTH-007).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { fetchAuthState, logout, type AuthState } from "@/app/lib/auth";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function AuthHeader() {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [state, setState] = useState<AuthState | null>(null);

  const refresh = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleLogout() {
    // Reuse the CSRF token from mount so logout is a single round-trip.
    const csrfToken =
      state && state.authenticated ? state.user.csrf_token : undefined;
    await logout(csrfToken);
    router.replace("/login");
  }

  return (
    <header className="flex h-12 items-center gap-2 border-b px-4">
      <SidebarTrigger />
      <div className="ml-auto flex items-center gap-2">
        {state && state.authenticated ? (
          <span className="text-sm text-muted-foreground">
            {state.user.email}
          </span>
        ) : null}
        <Button variant="ghost" size="sm" asChild>
          <Link href="/account">Account</Link>
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Toggle theme"
          onClick={() =>
            setTheme(resolvedTheme === "dark" ? "light" : "dark")
          }
        >
          <Sun className="hidden dark:block" />
          <Moon className="block dark:hidden" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleLogout}
        >
          Log out
        </Button>
      </div>
    </header>
  );
}
