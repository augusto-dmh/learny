// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InkLine } from "@/app/components/ink-line";

// POL-09/POL-11 — the shared signature rule: a token-only hairline whose fill
// exists only when it encodes real progress. The static header rule renders no
// fill at all.

afterEach(cleanup);

describe("InkLine", () => {
  it("renders the static rule without a fill when no percent is given", () => {
    render(<InkLine />);
    expect(screen.getByTestId("ink-line")).toBeTruthy();
    expect(screen.queryByTestId("ink-line-fill")).toBeNull();
  });

  it("fills proportionally to the given percent", () => {
    render(<InkLine percent={42} />);
    expect(screen.getByTestId("ink-line-fill").style.width).toBe("42%");
  });

  it("renders a zero-width fill at 0% instead of dropping it", () => {
    // Pins the `=== undefined` guard: 0 is defined-but-falsy, so a regression
    // to a falsy check would silently drop a just-started book's fill.
    render(<InkLine percent={0} />);
    expect(screen.getByTestId("ink-line-fill").style.width).toBe("0%");
  });

  it("clamps the fill to the 0..100 range", () => {
    render(<InkLine percent={140} />);
    expect(screen.getByTestId("ink-line-fill").style.width).toBe("100%");
    cleanup();
    render(<InkLine percent={-5} />);
    expect(screen.getByTestId("ink-line-fill").style.width).toBe("0%");
  });

  it("draws rail and ink from identity tokens", () => {
    render(<InkLine percent={10} />);
    expect(screen.getByTestId("ink-line").className).toContain("bg-border");
    expect(screen.getByTestId("ink-line-fill").className).toContain(
      "bg-primary",
    );
  });
});
