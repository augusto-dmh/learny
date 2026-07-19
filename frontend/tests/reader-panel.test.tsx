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

afterEach(cleanup);

describe("ReaderPanel shell (RA-01/02/03)", () => {
  it("offers exactly the Ask and Teach modes plus a close control", () => {
    render(
      <ReaderPanel mode="ask" onModeChange={() => {}} onClose={() => {}} />,
    );

    expect(screen.getByRole("tab", { name: "Ask" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Teach" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Close panel" })).toBeTruthy();
  });

  it("renders the ask body and selects the ask tab in ask mode (RA-01)", () => {
    render(
      <ReaderPanel mode="ask" onModeChange={() => {}} onClose={() => {}} />,
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
      <ReaderPanel mode="teach" onModeChange={() => {}} onClose={() => {}} />,
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
      <ReaderPanel mode="ask" onModeChange={onModeChange} onClose={() => {}} />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Teach" }));
    expect(onModeChange).toHaveBeenCalledWith("teach");
  });

  it("reports a close request when the close control is clicked (RA-03)", () => {
    const onClose = vi.fn();
    render(
      <ReaderPanel mode="ask" onModeChange={() => {}} onClose={onClose} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
