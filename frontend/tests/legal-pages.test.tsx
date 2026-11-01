// @vitest-environment jsdom

/**
 * DOOR-27..29 gate (component) — the public legal pages render signed-out from
 * the catalogs in the negotiated locale, with unique document titles and
 * bodies; /copyright shows the operator-configured DMCA mailbox read at render
 * time; /privacy names the two AI subprocessors without ever claiming
 * zero-data-retention, carries the LGPD data-subject rights (art. 18), the
 * international-transfer note and the ANPD route; and the terms state the
 * 18-or-older requirement the register flow attests.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CopyrightPage, { generateMetadata as copyrightMetadata } from "../app/copyright/page";
import PrivacyPage, { generateMetadata as privacyMetadata } from "../app/privacy/page";
import TermsPage, { generateMetadata as termsMetadata } from "../app/terms/page";
import { setTestLocale } from "./setup-intl";

afterEach(() => {
  cleanup();
  setTestLocale("en");
  vi.unstubAllEnvs();
});

describe("legal pages (DOOR-27)", () => {
  it("each page carries a distinct document title matching its document", async () => {
    const titles = [
      (await termsMetadata()).title,
      (await privacyMetadata()).title,
      (await copyrightMetadata()).title,
    ];
    expect(titles).toEqual(["Terms of Service", "Privacy Policy", "Copyright / DMCA"]);
    expect(new Set(titles).size).toBe(3);
  });

  it("each page renders its own unique heading and body", async () => {
    render(await TermsPage());
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Terms of Service",
    );
    const termsBody = document.body.textContent as string;
    cleanup();

    render(await PrivacyPage());
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Privacy Policy",
    );
    const privacyBody = document.body.textContent as string;
    cleanup();

    render(await CopyrightPage());
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
  it("shows the DMCA contact email configured in the environment", async () => {
    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "dmca@learny.example");

    render(await CopyrightPage());

    const link = screen.getByRole("link", { name: "dmca@learny.example" });
    expect(link.getAttribute("href")).toBe("mailto:dmca@learny.example");
  });

  it("reads the mailbox at render time, so a reconfigured operator address is what renders", async () => {
    // The value must be read inside the render: a module-scope read would bake
    // whichever value was loaded first into every later render.
    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "first@learny.example");
    render(await CopyrightPage());
    expect(screen.getByRole("link", { name: "first@learny.example" })).toBeTruthy();
    cleanup();

    vi.stubEnv("LEARNY_DMCA_CONTACT_EMAIL", "second@learny.example");
    render(await CopyrightPage());
    expect(screen.getByRole("link", { name: "second@learny.example" })).toBeTruthy();
  });

  it("renders the notice requirements as a list when no mailbox is configured", async () => {
    const { container } = render(await CopyrightPage());

    expect(container.textContent).toContain("(agent mailbox not configured)");
    const list = container.querySelector("ul");
    expect(list).not.toBeNull();
    expect(list!.querySelectorAll("li").length).toBeGreaterThanOrEqual(6);
    expect(container.querySelector('a[href="/terms"]')).not.toBeNull();
  });
});

describe("privacy page (DOOR-29)", () => {
  it("names OpenAI and Anthropic as the AI subprocessors", async () => {
    render(await PrivacyPage());

    const body = document.body.textContent as string;
    expect(body).toContain("OpenAI");
    expect(body).toContain("Anthropic");
  });

  it("never claims zero-data-retention", async () => {
    render(await PrivacyPage());

    const body = document.body.textContent as string;
    expect(body).not.toMatch(/zero[- ]data[- ]retention/i);
    expect(body).not.toMatch(/zero retention/i);
    expect(body).not.toMatch(/\bno retention\b/i);
  });

  it("carries the LGPD rights list, the transfer note, and the ANPD route", async () => {
    const { container } = render(await PrivacyPage());

    expect(screen.getByRole("heading", { name: "Your rights under the LGPD" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "International transfers" })).toBeTruthy();
    // The art. 18 enumeration renders as a real list, not one run-on paragraph.
    const list = container.querySelector("ul");
    expect(list).not.toBeNull();
    expect(list!.querySelectorAll("li").length).toBeGreaterThanOrEqual(9);
    expect(container.textContent).toContain("ANPD");
    // The adult-only posture is stated here too, and the cross-page link survives.
    expect(container.textContent).toContain("18 or older");
    expect(container.querySelector('a[href="/copyright"]')).not.toBeNull();
  });
});

describe("terms page", () => {
  it("states the 18-or-older requirement and links the privacy policy", async () => {
    const { container } = render(await TermsPage());

    expect(container.textContent).toContain("at least 18 years old");
    expect(container.querySelector('a[href="/copyright"]')).not.toBeNull();
    expect(container.querySelector('a[href="/privacy"]')).not.toBeNull();
  });
});

describe("legal pages under pt-BR", () => {
  it("render the pt-BR catalogs: headings, the rights list, and the age line", async () => {
    setTestLocale("pt-BR");
    render(await PrivacyPage());
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Política de Privacidade",
    );
    expect(
      screen.getByRole("heading", { name: "Seus direitos pela LGPD" }),
    ).toBeTruthy();
    expect(document.body.textContent as string).toContain("18 anos ou mais");
    expect(document.body.textContent as string).toContain("ANPD");
    cleanup();

    render(await TermsPage());
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Termos de Serviço",
    );
    expect(document.body.textContent as string).toContain("18 anos");
    cleanup();

    render(await CopyrightPage());
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Copyright / DMCA",
    );
    expect(document.body.textContent as string).toContain("(caixa do agente não configurada)");
  });
});
