// @vitest-environment jsdom

/**
 * C3 (component) — the reader capture popover carries the full five-verb selection
 * set when the reader wires the panel-bound verbs (RA-15): Highlight and Note run
 * the existing capture flow (RA-16), Explain and Ask hand the verbatim quote to
 * the reader, and Create card is a disabled "coming soon" placeholder that fires
 * nothing (RA-19). Absent those callbacks the popover stays the original
 * two-action capture control, byte-identical to the shipped highlight flow.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapturePopover } from "../app/components/notes/capture-popover";

afterEach(() => {
  cleanup();
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
  it("offers exactly five verbs when the panel-bound verbs are wired", () => {
    renderPopover({ quote: "a passage", onExplain: vi.fn(), onAskAbout: vi.fn() });

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
    renderPopover({ quote: "the selected sentence", onExplain, onAskAbout });

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
    });

    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));
    expect(onCapture).toHaveBeenCalledWith("highlight");
    fireEvent.click(screen.getByRole("button", { name: "Note" }));
    expect(onCapture).toHaveBeenCalledWith("highlight-note");
  });
});

describe("CapturePopover Create card (RA-19)", () => {
  it("shows a disabled Create card with a coming-soon hint that fires nothing", () => {
    const onCapture = vi.fn();
    renderPopover({
      quote: "a passage",
      onCapture,
      onExplain: vi.fn(),
      onAskAbout: vi.fn(),
    });

    const createCard = screen.getByRole("button", { name: "Create card" });
    expect((createCard as HTMLButtonElement).disabled).toBe(true);
    expect(createCard.getAttribute("title")).toBe("Coming soon");

    // A disabled button dispatches no click, so the placeholder triggers no action.
    fireEvent.click(createCard);
    expect(onCapture).not.toHaveBeenCalled();
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
