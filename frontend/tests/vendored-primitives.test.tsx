// @vitest-environment jsdom

/**
 * The vendored shadcn primitives ship English default text (the dialog and sheet
 * close controls, the mobile sidebar's title and description, the sidebar
 * toggle, the spinner's status label). That text is interface language, so it
 * comes from the catalog in every locale rather than from the vendored source.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "../components/ui/sheet";
import {
  Sidebar,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "../components/ui/sidebar";
import { Spinner } from "../components/ui/spinner";
import type { AppLocale } from "../i18n/config";
import { setTestLocale } from "./setup-intl";

const COPY: Record<
  AppLocale,
  { close: string; loading: string; toggle: string; title: string; description: string }
> = {
  en: {
    close: "Close",
    loading: "Loading",
    toggle: "Toggle Sidebar",
    title: "Sidebar",
    description: "Displays the mobile sidebar.",
  },
  "pt-BR": {
    close: "Fechar",
    loading: "Carregando",
    toggle: "Alternar barra lateral",
    title: "Barra lateral",
    description: "Mostra a barra lateral no celular.",
  },
};

const desktopWidth = window.innerWidth;

beforeEach(() => {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
});

afterEach(() => {
  cleanup();
  window.innerWidth = desktopWidth;
});

describe("vendored primitives", () => {
  describe.each(["en", "pt-BR"] as const)("in %s", (locale) => {
    const copy = COPY[locale];

    it("default text comes from the catalog", () => {
      setTestLocale(locale);

      render(
        <Dialog open>
          <DialogContent>
            <DialogTitle>Dialog</DialogTitle>
            <DialogDescription>Body</DialogDescription>
            <DialogFooter showCloseButton />
          </DialogContent>
        </Dialog>,
      );
      // The corner close control and the footer close button.
      expect(screen.getAllByRole("button", { name: copy.close })).toHaveLength(2);
      cleanup();

      render(
        <Sheet open>
          <SheetContent>
            <SheetTitle>Sheet</SheetTitle>
            <SheetDescription>Body</SheetDescription>
          </SheetContent>
        </Sheet>,
      );
      expect(screen.getByRole("button", { name: copy.close })).toBeTruthy();
      cleanup();

      render(<Spinner />);
      expect(screen.getByRole("status", { name: copy.loading })).toBeTruthy();
      cleanup();

      render(
        <SidebarProvider>
          <Sidebar>
            <SidebarRail />
          </Sidebar>
          <SidebarTrigger />
        </SidebarProvider>,
      );
      // The header trigger and the edge rail.
      expect(screen.getAllByRole("button", { name: copy.toggle })).toHaveLength(2);
      const rail = document.querySelector('[data-slot="sidebar-rail"]');
      expect(rail?.getAttribute("aria-label")).toBe(copy.toggle);
      expect(rail?.getAttribute("title")).toBe(copy.toggle);
    });

    it("names the mobile sidebar sheet from the catalog", () => {
      setTestLocale(locale);
      window.innerWidth = 500;

      render(
        <SidebarProvider>
          <Sidebar>
            <p>nav</p>
          </Sidebar>
          <SidebarTrigger />
        </SidebarProvider>,
      );
      fireEvent.click(screen.getByRole("button", { name: copy.toggle }));

      expect(screen.getByRole("dialog", { name: copy.title })).toBeTruthy();
      expect(screen.getByText(copy.description)).toBeTruthy();
    });
  });
});
