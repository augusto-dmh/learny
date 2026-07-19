// @vitest-environment jsdom

/**
 * A (RA-01/02/03) — the reader side-panel shell hosts an Ask | Teach segmented
 * control and a close control. It renders the body for the active mode, marks the
 * active tab as selected, and reports mode switches and close through its
 * callbacks (the parent turns those into URL changes). Open state and mode are
 * driven entirely by props derived from `?panel=`, so the shell itself is a pure
 * function of `mode`.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReaderPanel } from "../app/components/reader-panel";

// The shell test covers tabs, close, and which mode's body renders — not the
// chat internals (unit-tested in ask-panel.test.tsx, which pull in AI-Elements).
// Stub the ported bodies to their markers so the shell stays a pure unit test;
// each stub also surfaces its `onShowInBook` prop through a button so the shell's
// forwarding of the citation-jump callback to BOTH modes can be driven by a click.
vi.mock("../app/components/ask-panel", () => ({
  AskPanel: ({ onShowInBook }: { onShowInBook?: (anchor: string) => void }) => (
    <div data-testid="ask-panel-body">
      <button type="button" onClick={() => onShowInBook?.("ask#anchor")}>
        ask-show-in-book
      </button>
    </div>
  ),
}));
vi.mock("../app/components/teach-panel", () => ({
  TeachPanel: ({ onShowInBook }: { onShowInBook?: (anchor: string) => void }) => (
    <div data-testid="teach-panel-body">
      <button type="button" onClick={() => onShowInBook?.("teach#anchor")}>
        teach-show-in-book
      </button>
    </div>
  ),
}));

afterEach(cleanup);

describe("ReaderPanel shell (RA-01/02/03)", () => {
  it("offers exactly the Ask and Teach modes plus a close control", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByRole("tab", { name: "Ask" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Teach" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Close panel" })).toBeTruthy();
  });

  it("renders the ask body and selects the ask tab in ask mode (RA-01)", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByTestId("ask-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("teach-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Ask" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      screen.getByRole("tab", { name: "Teach" }).getAttribute("aria-selected"),
    ).toBe("false");
  });

  it("renders the teach body and selects the teach tab in teach mode (RA-02)", () => {
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="teach" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByTestId("teach-panel-body")).toBeTruthy();
    expect(screen.queryByTestId("ask-panel-body")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "Teach" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("reports the chosen mode when a tab is clicked (RA-03)", () => {
    const onModeChange = vi.fn();
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={onModeChange} onClose={() => {}} />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));
    expect(onModeChange).toHaveBeenCalledWith("teach");
  });

  it("reports a close request when the close control is clicked (RA-03)", () => {
    const onClose = vi.fn();
    render(
      <ReaderPanel sourceId="s1" csrf="csrf-xyz" mode="ask" onModeChange={() => {}} onClose={onClose} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("forwards the show-in-book callback to the active mode body (RA-13/14)", () => {
    const onShowInBook = vi.fn();

    // Ask mode: the ask body's jump reaches the shell's callback with its anchor.
    const { rerender } = render(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        mode="ask"
        onModeChange={() => {}}
        onClose={() => {}}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "ask-show-in-book" }));
    expect(onShowInBook).toHaveBeenCalledWith("ask#anchor");

    // Teach mode: the teach body's jump reaches the same callback — both wired.
    rerender(
      <ReaderPanel
        sourceId="s1"
        csrf="csrf-xyz"
        mode="teach"
        onModeChange={() => {}}
        onClose={() => {}}
        onShowInBook={onShowInBook}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "teach-show-in-book" }));
    expect(onShowInBook).toHaveBeenCalledWith("teach#anchor");
  });
});
