// @vitest-environment jsdom

/**
 * C3 (component) — the reader capture popover carries the full five-verb selection
 * set when the reader wires the panel- and card-bound verbs (RA-15): Highlight and
 * Note run the existing capture flow (RA-16), Explain and Ask hand the verbatim
 * quote to the reader, and Create card starts the capture-to-card flow the reader
 * owns (CAP-01). Absent those callbacks the popover stays the original two-action
 * capture control, byte-identical to the shipped highlight flow.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapturePopover } from "../app/components/notes/capture-popover";
import { LG_MIN_WIDTH_PX } from "../hooks/use-below-lg";

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(window, "matchMedia");
});

/** Render the popover; every render supplies the capture-flow essentials. */
function renderPopover(
  props: Partial<React.ComponentProps<typeof CapturePopover>> = {},
) {
  return render(
    <CapturePopover
      top={0}
      left={0}
      pending={false}
      error={null}
      onCapture={props.onCapture ?? vi.fn()}
      {...props}
    />,
  );
}

describe("CapturePopover five verbs (RA-15)", () => {
  it("offers exactly five verbs when the panel- and card-bound verbs are wired", () => {
    renderPopover({
      quote: "a passage",
      onExplain: vi.fn(),
      onAskAbout: vi.fn(),
      onCreateCard: vi.fn(),
    });

    const dialog = screen.getByRole("dialog", { name: "Capture highlight" });
    const buttons = within(dialog).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual([
      "Highlight",
      "Note",
      "Explain",
      "Ask",
      "Create card",
    ]);
  });

  it("Explain and Ask carry the verbatim quote up to the reader (RA-17/18)", () => {
    const onExplain = vi.fn();
    const onAskAbout = vi.fn();
    renderPopover({
      quote: "the selected sentence",
      onExplain,
      onAskAbout,
      onCreateCard: vi.fn(),
    });

    fireEvent.click(screen.getByRole("button", { name: "Explain" }));
    expect(onExplain).toHaveBeenCalledTimes(1);
    expect(onExplain).toHaveBeenCalledWith("the selected sentence");

    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(onAskAbout).toHaveBeenCalledTimes(1);
    expect(onAskAbout).toHaveBeenCalledWith("the selected sentence");
  });

  it("Highlight and Note run the existing capture flow unchanged (RA-16)", () => {
    const onCapture = vi.fn();
    renderPopover({
      quote: "a passage",
      onCapture,
      onExplain: vi.fn(),
      onAskAbout: vi.fn(),
      onCreateCard: vi.fn(),
    });

    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));
    expect(onCapture).toHaveBeenCalledWith("highlight");
    fireEvent.click(screen.getByRole("button", { name: "Note" }));
    expect(onCapture).toHaveBeenCalledWith("highlight-note");
  });
});

describe("CapturePopover Create card (CAP-01)", () => {
  it("is a live verb that hands the card flow to the reader", () => {
    const onCapture = vi.fn();
    const onCreateCard = vi.fn();
    renderPopover({
      quote: "a passage",
      onCapture,
      onExplain: vi.fn(),
      onAskAbout: vi.fn(),
      onCreateCard,
    });

    const createCard = screen.getByRole("button", { name: "Create card" });
    // No longer a placeholder: it is enabled and carries no coming-soon hint.
    expect((createCard as HTMLButtonElement).disabled).toBe(false);
    expect(createCard.getAttribute("title")).toBeNull();

    fireEvent.click(createCard);
    expect(onCreateCard).toHaveBeenCalledTimes(1);
    // The card flow is its own verb — it does not run the plain capture action.
    expect(onCapture).not.toHaveBeenCalled();
  });

  it("disables while a capture or generation is in flight", () => {
    const onCreateCard = vi.fn();
    renderPopover({
      quote: "a passage",
      pending: true,
      onExplain: vi.fn(),
      onAskAbout: vi.fn(),
      onCreateCard,
    });

    const createCard = screen.getByRole("button", { name: "Create card" });
    expect((createCard as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(createCard);
    expect(onCreateCard).not.toHaveBeenCalled();
  });
});

describe("CapturePopover without verbs (RA-16)", () => {
  it("stays the original two-action capture popover when the verbs are not wired", () => {
    renderPopover();

    const dialog = screen.getByRole("dialog", { name: "Capture highlight" });
    const buttons = within(dialog).getAllByRole("button");
    // Byte-identical to the shipped popover: just Highlight and Highlight + note.
    expect(buttons.map((b) => b.textContent)).toEqual([
      "Highlight",
      "Highlight + note",
    ]);
    expect(screen.queryByRole("button", { name: "Explain" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Create card" })).toBeNull();
  });
});

function stubViewportWidth(width: number) {
  window.matchMedia = (query: string) => {
    const maxWidth = query.match(/max-width:\s*(\d+)px/i);
    const matches = maxWidth ? width <= Number(maxWidth[1]) : false;
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  };
}

const FIVE_VERBS = {
  quote: "a passage",
  onExplain: vi.fn(),
  onAskAbout: vi.fn(),
  onCreateCard: vi.fn(),
};

describe("CapturePopover compact bar below lg (READ-24)", () => {
  it("keeps Highlight as the visible primary and hides the rest behind overflow", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX - 1);
    renderPopover(FIVE_VERBS);

    const overflow = await waitFor(() =>
      screen.getByRole("button", { name: "More capture actions" }),
    );
    const row = screen.getByTestId("capture-verb-row");
    expect(within(row).getByRole("button", { name: "Highlight" })).toBeTruthy();
    expect(within(row).queryByRole("button", { name: "Explain" })).toBeNull();
    expect(within(row).queryByRole("button", { name: "Ask" })).toBeNull();
    expect(within(row).queryByRole("button", { name: "Note" })).toBeNull();
    expect(within(row).queryByRole("button", { name: "Create card" })).toBeNull();

    fireEvent.click(overflow);
    expect(screen.getByRole("button", { name: "Note" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Explain" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create card" })).toBeTruthy();
  });

  it("still offers the five-verb bar at lg and above", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX);
    renderPopover(FIVE_VERBS);

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "More capture actions" })).toBeNull();
    });
    const dialog = screen.getByRole("dialog", { name: "Capture highlight" });
    expect(
      within(dialog)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["Highlight", "Note", "Explain", "Ask", "Create card"]);
  });
});

describe("CapturePopover control targets (READ-25)", () => {
  it("sizes Highlight to at least 44px", () => {
    renderPopover(FIVE_VERBS);
    const highlight = screen.getByRole("button", { name: "Highlight" });
    expect(Number.parseFloat(getComputedStyle(highlight).minWidth)).toBeGreaterThanOrEqual(44);
    expect(Number.parseFloat(getComputedStyle(highlight).minHeight)).toBeGreaterThanOrEqual(44);
  });

  it("sizes the overflow control to at least 44px below lg", async () => {
    stubViewportWidth(LG_MIN_WIDTH_PX - 1);
    renderPopover(FIVE_VERBS);
    const overflow = await waitFor(() =>
      screen.getByRole("button", { name: "More capture actions" }),
    );
    expect(Number.parseFloat(getComputedStyle(overflow).minWidth)).toBeGreaterThanOrEqual(44);
    expect(Number.parseFloat(getComputedStyle(overflow).minHeight)).toBeGreaterThanOrEqual(44);
  });
});
