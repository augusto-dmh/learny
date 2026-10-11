// @vitest-environment jsdom

/**
 * D2 gate (component) — auth screens drive the proxy through the auth client,
 * logout carries the CSRF header, and the unauthenticated redirect is UX-only
 * (AC-2/AC-3, FR-AUTH-007).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "../app/(auth)/login/page";
import RegisterPage from "../app/(auth)/register/page";
import { AccountPanel } from "../app/components/AccountPanel";
import { AuthForm } from "../app/components/AuthForm";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

// The sign-in pages route through the app router after authenticating.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));

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

  it("register collects the invite code and ToS consent and posts both", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(201, { id: "u1", email: "a@b.c", created_at: "now" }));
    vi.stubGlobal("fetch", fetchMock);

    const onAuthenticated = vi.fn();
    render(<AuthForm mode="register" onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.change(screen.getByLabelText(/Invite code/), { target: { value: "WELCOME" } });
    fireEvent.click(screen.getByLabelText(/Terms of Service/));
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledTimes(1));
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("same-origin");
    // Exact payload: the invite and consent ride along — and the exact key set
    // proves no captcha/Turnstile token field is ever posted.
    expect(JSON.parse(init.body as string)).toEqual({
      email: "a@b.c",
      password: "pw",
      invite_code: "WELCOME",
      accepted_tos: true,
    });
  });

  it("register requires the ToS checkbox client-side and links the terms", () => {
    render(<AuthForm mode="register" />);

    const checkbox = screen.getByLabelText(/Terms of Service/) as HTMLInputElement;
    expect(checkbox.type).toBe("checkbox");
    // Native `required` blocks submit until the learner consents.
    expect(checkbox.required).toBe(true);

    const termsLink = screen.getByRole("link", { name: "Terms of Service" });
    expect(termsLink.getAttribute("href")).toBe("/terms");
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
          ai_profile_id: null,
        }),
      )
      // the account panel's AI-profile section load (catalog + stored choice);
      // this deployment's catalog is empty, so the section stays absent.
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(jsonResponse(200, { profile_id: null }))
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

describe("auth screens in pt-BR", () => {
  it("renders in pt-BR", () => {
    setTestLocale("pt-BR");

    render(<LoginPage />);
    expect(screen.getByText("Que bom ter você de volta ao Learny.")).toBeTruthy();
    expect(screen.getByRole("form", { name: "formulário de entrada" })).toBeTruthy();
    expect(screen.getByLabelText("E-mail")).toBeTruthy();
    expect(screen.getByLabelText("Senha")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Crie uma" }).getAttribute("href"),
    ).toBe("/register");
    expectNoEnglishCopy(document.body.textContent ?? "", "auth");
    cleanup();

    render(<RegisterPage />);
    expect(screen.getByText("Comece a aprender com o Learny.")).toBeTruthy();
    expect(screen.getByRole("form", { name: "formulário de cadastro" })).toBeTruthy();
    expect(screen.getByLabelText(/Código de convite/)).toBeTruthy();
    expect(screen.getByLabelText(/Termos de Serviço/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Criar conta" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Entre" }).getAttribute("href"),
    ).toBe("/login");
    expectNoEnglishCopy(document.body.textContent ?? "", "auth");
  });

  it("shows a failed sign-in in Portuguese", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(401, { detail: "Invalid email or password." })),
    );
    render(<AuthForm mode="login" />);

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("E-mail ou senha inválidos.");
  });
});

describe("AuthForm in-flight label", () => {
  it.each([
    ["en", "Working…"],
    ["pt-BR", "Aguarde…"],
  ] as const)("shows a disabled in-flight button in %s", async (locale, label) => {
    setTestLocale(locale);
    // A sign-in that never settles holds the form in flight.
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<AuthForm mode="login" />);

    fireEvent.submit(screen.getByRole("form"));

    const button = (await screen.findByRole("button", { name: label })) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });
});
