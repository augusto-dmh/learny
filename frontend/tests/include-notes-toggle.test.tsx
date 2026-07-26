// @vitest-environment jsdom

/**
 * The notes-scope control has to say what it does. Its label names the effect —
 * what gets searched — rather than describing the notes as an ingredient, and an
 * explanatory description is reachable from the control itself, so a reader can
 * find out why the same question answers differently with it on.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IncludeNotesToggle } from "../app/components/include-notes-toggle";

afterEach(cleanup);

describe("IncludeNotesToggle", () => {
  it("names the effect on what is searched", () => {
    render(<IncludeNotesToggle checked={false} onChange={() => {}} />);

    expect(
      screen.getByRole("checkbox", { name: "Search my notes too" }),
    ).toBeTruthy();
  });

  it("carries an explanation of what it changes, reachable from the control", () => {
    render(<IncludeNotesToggle checked={false} onChange={() => {}} />);

    const control = screen.getByRole("checkbox");
    const describedBy = control.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();

    const description = document.getElementById(describedBy!);
    expect(description).toBeTruthy();
    // The explanation is about what gets searched and grounded, not about style.
    expect(description!.textContent).toMatch(/your own notes/i);
    expect(description!.textContent).toMatch(/searched/i);
    expect(description!.textContent).toMatch(/grounded/i);
  });

  it("reports a flip and reflects the given state", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <IncludeNotesToggle checked={false} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);

    rerender(<IncludeNotesToggle checked onChange={onChange} />);
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  });
});
