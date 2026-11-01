/**
 * The one money formatter (S4/S5): a nonzero cost under the four-decimal
 * floor carries an explicit less-than floor so a call that cost the learner
 * something never displays as $0, and every other amount reads through Intl
 * in the interface locale — en dot, pt-BR comma, US$ symbol. Exact strings
 * are asserted only where Intl's output is stable (nonzero digits at every
 * rendered position); trailing-zero padding is the locale's business.
 */
import { describe, expect, it } from "vitest";

import { formatUsdMicros } from "../app/lib/money";

describe("formatUsdMicros", () => {
  it("a nonzero cost under 100 micros takes the floor instead of rendering $0", () => {
    // 49 micros would round to $0 at four decimals; the floor says less-than.
    expect(formatUsdMicros(1, "en")).toBe("<$0.0001");
    expect(formatUsdMicros(49, "en")).toBe("<$0.0001");
    expect(formatUsdMicros(99, "en")).toBe("<$0.0001");
  });

  it("the floor renders with the locale's own symbol and separators in pt-BR", () => {
    expect(formatUsdMicros(49, "pt-BR")).toBe("<US$\u00A00,0001");
  });

  it("amounts at and above the floor read through the four-decimal format unchanged", () => {
    expect(formatUsdMicros(100, "en")).toBe("$0.0001");
    expect(formatUsdMicros(10_500, "en")).toBe("$0.0105");
    expect(formatUsdMicros(221_000, "en")).toBe("$0.221");
    expect(formatUsdMicros(10_500, "pt-BR")).toBe("US$\u00A00,0105");
  });

  it("a true zero still reads as zero — the floor is for costs that were paid", () => {
    expect(formatUsdMicros(0, "en")).toMatch(/^\$0(\.00)?$/);
    expect(formatUsdMicros(0, "pt-BR")).toMatch(/^US\$\u00A00(,00)?$/);
  });
});
