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

  it("stops taking input and explains itself once a conversation fixed the choice", () => {
    render(<IncludeNotesToggle checked onChange={() => {}} locked />);

    // Disabled, so the browser gives the reader no way to flip it.
    const control = screen.getByRole("checkbox") as HTMLInputElement;
    expect(control.disabled).toBe(true);

    // The explanation says what the control now applies to, and what to do about it.
    const description = document.getElementById(
      control.getAttribute("aria-describedby")!,
    );
    expect(description!.textContent).toMatch(/this conversation was started/i);
    expect(description!.textContent).toMatch(/start a new one to change it/i);
  });
});
