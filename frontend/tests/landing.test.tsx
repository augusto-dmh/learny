// @vitest-environment jsdom

/**
 * C gate (component) — the public landing page (HOME-20). An anonymous visitor
 * sees the product name, a one-line value proposition, and both entry CTAs
 * (Create account → /register, Log in → /login). Identity styling (Iron Gall
 * tokens) and light/dark rendering are CSS-token concerns not observable in
 * jsdom — recorded as sensor-blind and verified by a human eye.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import LandingPage from "../app/page";

afterEach(() => {
  cleanup();
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
});
