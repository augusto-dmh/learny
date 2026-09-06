"use client";

/**
 * Minimal email/password form for register and login (D2).
 *
 * Pure presentation + a submit handler that calls the proxy via the auth client.
 * It holds no session token (the cookie is HttpOnly); it only collects inputs
 * and surfaces success/error. FastAPI validates email/password authoritatively.
 */

import { useState } from "react";
import Link from "next/link";

import { login, register, type UserSummary } from "@/app/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type AuthMode = "login" | "register";

export function AuthForm({
  mode,
  onAuthenticated,
}: {
  mode: AuthMode;
  onAuthenticated?: (user: UserSummary) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [acceptedTos, setAcceptedTos] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submitLabel = mode === "register" ? "Create account" : "Log in";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "register") {
        const user = await register(email, password, {
          acceptedTos,
          inviteCode: inviteCode.trim() || undefined,
        });
        onAuthenticated?.(user);
      } else {
        const user = await login(email, password);
        onAuthenticated?.(user);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={`${mode} form`}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <label htmlFor="auth-email" className="text-sm font-medium">
          Email
        </label>
        <Input
          id="auth-email"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="auth-password" className="text-sm font-medium">
          Password
        </label>
        <Input
          id="auth-password"
          type="password"
          name="password"
          autoComplete={mode === "register" ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      {mode === "register" ? (
        <>
          <div className="space-y-1.5">
            <label htmlFor="auth-invite" className="text-sm font-medium">
              Invite code{" "}
              <span className="font-normal text-muted-foreground">(if you have one)</span>
            </label>
            <Input
              id="auth-invite"
              type="text"
              name="invite_code"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
            />
          </div>
          <div className="flex items-start gap-2">
            <input
              id="auth-tos"
              type="checkbox"
              name="accepted_tos"
              checked={acceptedTos}
              onChange={(e) => setAcceptedTos(e.target.checked)}
              required
              className="mt-1 size-4 accent-primary"
            />
            <label htmlFor="auth-tos" className="text-sm">
              I agree to the{" "}
              <Link
                href="/terms"
                className="text-primary underline-offset-4 hover:underline"
              >
                Terms of Service
              </Link>
            </label>
          </div>
        </>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Working…" : submitLabel}
      </Button>
    </form>
  );
}
