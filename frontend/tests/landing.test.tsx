// @vitest-environment jsdom

/**
 * C gate (component) — the public landing page (HOME-20). An anonymous visitor
 * sees the product name, a one-line value proposition, and both entry CTAs
 * (Create account → /register, Log in → /login). Identity styling (Iron Gall
 * tokens) and light/dark rendering are CSS-token concerns not observable in
 * jsdom — recorded as sensor-blind and verified by a human eye.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LandingPage from "../app/page";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

// The page hosts the anonymous language switcher, which re-renders through the router.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Landing page (HOME-20)", () => {
  it("shows the product name and a one-line value proposition", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("heading", { level: 1 }).textContent,
    ).toBe("Learny");
    expect(
      screen.getByText("Turn your books into cited answers and lasting recall."),
    ).toBeTruthy();
  });

  it("offers a Create account CTA linking to /register", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("link", { name: "Create account" }).getAttribute("href"),
    ).toBe("/register");
  });

  it("offers a Log in CTA linking to /login", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("link", { name: "Log in" }).getAttribute("href"),
    ).toBe("/login");
  });

  it("shows a cited-answer proof above the account CTAs", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<LandingPage />);

    const proof = screen.getByText("All warfare is based on deception.");
    const createAccount = screen.getByRole("link", { name: "Create account" });
    const logIn = screen.getByRole("link", { name: "Log in" });

    expect(screen.getByText("The Art of War")).toBeTruthy();
    expect(screen.getByText("I. Laying Plans")).toBeTruthy();
    expect(
      proof.compareDocumentPosition(createAccount) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      proof.compareDocumentPosition(logIn) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders in pt-BR", () => {
    setTestLocale("pt-BR");
    render(<LandingPage />);

    expect(
      screen.getByText(
        "Transforme seus livros em respostas com citações e em conhecimento que fica.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Criar conta" }).getAttribute("href"),
    ).toBe("/register");
    expect(
      screen.getByRole("link", { name: "Entrar" }).getAttribute("href"),
    ).toBe("/login");
    expect(screen.getByRole("combobox", { name: "Idioma" })).toBeTruthy();
    expectNoEnglishCopy(document.body.textContent ?? "", "landing", "auth", "common");
  });

  it("keeps the book proof verbatim in the book's language under pt-BR", () => {
    setTestLocale("pt-BR");
    render(<LandingPage />);

    const quote = screen.getByText("All warfare is based on deception.");
    expect(quote.getAttribute("lang")).toBe("en");
    expect(screen.getByText("The Art of War").getAttribute("lang")).toBe("en");
    expect(screen.getByText("I. Laying Plans").getAttribute("lang")).toBe("en");
  });
});
