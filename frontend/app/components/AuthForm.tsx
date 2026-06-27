"use client";

/**
 * Minimal email/password form for register and login (D2).
 *
 * Pure presentation + a submit handler that calls the proxy via the auth client.
 * It holds no session token (the cookie is HttpOnly); it only collects inputs
 * and surfaces success/error. FastAPI validates email/password authoritatively.
 */

import { useState } from "react";

import { login, register, type UserSummary } from "@/app/lib/auth";

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
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submitLabel = mode === "register" ? "Create account" : "Log in";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const action = mode === "register" ? register : login;
      const user = await action(email, password);
      onAuthenticated?.(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label={`${mode} form`}>
      <label>
        Email
        <input
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </label>
      <label>
        Password
        <input
          type="password"
          name="password"
          autoComplete={mode === "register" ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? "Working…" : submitLabel}
      </button>
    </form>
  );
}
