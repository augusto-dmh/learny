// @vitest-environment jsdom

/**
 * A turn that grounds nothing has two different meanings and the reader is told
 * which. "Nothing in this book" is a dead end. "Nothing in the part of the book
 * this conversation covers" is not — the answer may sit a few chapters away, and
 * a reader told the first thing when the second is true would wrongly give up.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NotFoundNotice } from "../app/components/not-found-notice";

afterEach(cleanup);

describe("NotFoundNotice", () => {
  it("tells a scoped miss apart from a whole-book miss", () => {
    const { unmount } = render(<NotFoundNotice status="not_found_in_scope" />);
    const scoped = screen.getByTestId("not-found").textContent ?? "";
    unmount();

    render(<NotFoundNotice status="not_found_in_source" />);
    const wholeBook = screen.getByTestId("not-found").textContent ?? "";

    // A scoped miss points the reader at the rest of the book; a whole-book miss
    // does not, because there is nowhere else to look.
    expect(scoped).not.toBe(wholeBook);
    expect(scoped).toMatch(/elsewhere in the book/i);
    expect(wholeBook).toMatch(/not found in this book/i);
    expect(wholeBook).not.toMatch(/elsewhere/i);
  });
});
