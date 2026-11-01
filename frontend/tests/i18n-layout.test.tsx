// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useTranslations } from "use-intl";

import en from "@/messages/en.json";
import ptBR from "@/messages/pt-BR.json";

import { setTestLocale } from "./setup-intl";

// next/font only works inside a Next build; the layout just needs its `variable`.
vi.mock("next/font/google", () => ({
  Source_Serif_4: () => ({ variable: "font-serif-var" }),
}));
vi.mock("geist/font/sans", () => ({ GeistSans: { variable: "font-sans-var" } }));

afterEach(cleanup);

async function rootElement() {
  const { default: RootLayout } = await import("@/app/layout");
  return (await RootLayout({ children: null })) as { type: string; props: { lang: string } };
}

describe("root layout", () => {
  it("html lang follows the locale", async () => {
    setTestLocale("en");
    expect((await rootElement()).props.lang).toBe("en");
    setTestLocale("pt-BR");
    expect((await rootElement()).props.lang).toBe("pt-BR");
  });

  it("generates metadata from the active catalog", async () => {
    const { generateMetadata } = await import("@/app/layout");
    setTestLocale("pt-BR");
    expect(await generateMetadata()).toEqual({
      title: ptBR.meta.title,
      description: ptBR.meta.description,
      // The static manifest link rides along; it is not locale-dependent.
      manifest: "/manifest.webmanifest",
    });
    setTestLocale("en");
    expect(await generateMetadata()).toEqual({
      title: en.meta.title,
      description: en.meta.description,
      manifest: "/manifest.webmanifest",
    });
  });
});

describe("the real client provider", () => {
  function Probe() {
    const t = useTranslations("common");
    return <p>{t("loading")}</p>;
  }

  it("serves the catalog the layout hands it", () => {
    render(
      <NextIntlClientProvider locale="pt-BR" messages={ptBR}>
        <Probe />
      </NextIntlClientProvider>,
    );
    expect(screen.getByText(ptBR.common.loading)).toBeTruthy();
  });
});
