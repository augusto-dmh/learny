// @vitest-environment jsdom

/**
 * D2 gate (component) — auth screens drive the proxy through the auth client,
 * logout carries the CSRF header, and the unauthenticated redirect is UX-only
 * (AC-2/AC-3, FR-AUTH-007).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountPanel } from "../app/components/AccountPanel";
import { AuthForm } from "../app/components/AuthForm";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AuthForm (D2)", () => {
  it("submitting login calls the proxy /api/auth/login and reports success", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { id: "u1", email: "a@b.c", created_at: "now" }));
    vi.stubGlobal("fetch", fetchMock);

    const onAuthenticated = vi.fn();
    render(<AuthForm mode="login" onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/login");
  });

  it("renders the backend error and does not authenticate on failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(401, { detail: "Invalid email or password." }));
    vi.stubGlobal("fetch", fetchMock);

    const onAuthenticated = vi.fn();
    render(<AuthForm mode="login" onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Invalid email or password.");
    expect(onAuthenticated).not.toHaveBeenCalled();
  });
});

describe("AccountPanel (D2)", () => {
  it("renders the signed-in user and logout sends X-CSRF-Token", async () => {
    const fetchMock = vi
      .fn()
      // initial /me (mount) — authenticated, carries csrf token
      .mockResolvedValueOnce(
        jsonResponse(200, {
          id: "u1",
          email: "a@b.c",
          created_at: "now",
          csrf_token: "csrf-xyz",
        }),
      )
      // the logout POST itself — the token from mount is reused, so there is no
      // second /me probe.
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const onLoggedOut = vi.fn();
    render(<AccountPanel onLoggedOut={onLoggedOut} />);

    await screen.findByText("a@b.c");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(onLoggedOut).toHaveBeenCalledTimes(1));

    const logoutCall = fetchMock.mock.calls.find((c) => c[0] === "/api/auth/logout");
    expect(logoutCall).toBeDefined();
    const headers = new Headers(logoutCall![1].headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    // The mount token is reused: exactly one /me call, no extra logout probe.
    const meCalls = fetchMock.mock.calls.filter((c) => c[0] === "/api/auth/me");
    expect(meCalls).toHaveLength(1);
  });

  it("fires the UX-only redirect callback when unauthenticated (not a security boundary)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    const onRequireAuth = vi.fn();
    render(<AccountPanel onRequireAuth={onRequireAuth} />);

    await waitFor(() => expect(onRequireAuth).toHaveBeenCalledTimes(1));
    // The redirect is client-side convenience only; FastAPI is the real gate.
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});
