// @vitest-environment jsdom

/**
 * DOOR-27..29 gate (component) — the public legal pages render signed-out with
 * unique document titles and bodies, /copyright shows the operator-configured
 * DMCA mailbox read at render time, and /privacy names the two AI
 * subprocessors without ever claiming zero-data-retention.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CopyrightPage, { metadata as copyrightMetadata } from "../app/copyright/page";
import PrivacyPage, { metadata as privacyMetadata } from "../app/privacy/page";
import TermsPage, { metadata as termsMetadata } from "../app/terms/page";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("legal pages (DOOR-27)", () => {
  it("each page carries a distinct document title matching its document", () => {
    const titles = [
      termsMetadata.title,
      privacyMetadata.title,
      copyrightMetadata.title,
    ];
    expect(titles).toEqual(["Terms of Service", "Privacy Policy", "Copyright / DMCA"]);
    expect(new Set(titles).size).toBe(3);
  });

  it("each page renders its own unique heading and body", () => {
    render(<TermsPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Terms of Service",
    );
    const termsBody = document.body.textContent as string;
    cleanup();

    render(<PrivacyPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Privacy Policy",
    );
    const privacyBody = document.body.textContent as string;
    cleanup();

    render(<CopyrightPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Copyright / DMCA",
    );
    const copyrightBody = document.body.textContent as string;

    expect(termsBody).not.toBe(privacyBody);
    expect(termsBody).not.toBe(copyrightBody);
    expect(privacyBody).not.toBe(copyrightBody);
  });
});

describe("copyright page (DOOR-28)", () => {
  it("shows the DMCA contact email configured in the environment", () => {
    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "dmca@learny.example");

    render(<CopyrightPage />);

    const link = screen.getByRole("link", { name: "dmca@learny.example" });
    expect(link.getAttribute("href")).toBe("mailto:dmca@learny.example");
  });

  it("reads the mailbox at render time, so a reconfigured operator address is what renders", () => {
    // The value must be read inside the render: a module-scope read would bake
    // whichever value was loaded first into every later render.
    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "first@learny.example");
    render(<CopyrightPage />);
    expect(screen.getByRole("link", { name: "first@learny.example" })).toBeTruthy();
    cleanup();

    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "second@learny.example");
    render(<CopyrightPage />);
    expect(screen.getByRole("link", { name: "second@learny.example" })).toBeTruthy();
  });
});

describe("privacy page (DOOR-29)", () => {
  it("names OpenAI and Anthropic as the AI subprocessors", () => {
    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "dmca@learny.example");
    render(<PrivacyPage />);

    expect(screen.getByText("OpenAI")).toBeTruthy();
    expect(screen.getByText("Anthropic")).toBeTruthy();
  });

  it("never claims zero-data-retention", () => {
    render(<PrivacyPage />);

    const body = document.body.textContent as string;
    expect(body).not.toMatch(/zero[- ]data[- ]retention/i);
    expect(body).not.toMatch(/zero retention/i);
    expect(body).not.toMatch(/\bno retention\b/i);
  });
});
