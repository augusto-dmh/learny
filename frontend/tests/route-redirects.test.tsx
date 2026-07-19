/**
 * A (RA-04) — the standalone Ask and Teach routes are now tombstones that
 * redirect into the reader with the matching panel open. Each page is a server
 * component that awaits its dynamic `params` (Next 15) and calls `redirect()`
 * with the exact reader deep link, so old links and bookmarks still land inside
 * the book.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const redirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
}));

import AskPage from "../app/(app)/sources/[id]/ask/page";
import TeachPage from "../app/(app)/sources/[id]/teach/page";

beforeEach(() => {
  redirect.mockClear();
});

describe("Ask/Teach route redirects (RA-04)", () => {
  it("redirects the ask route into the reader ask panel", async () => {
    await AskPage({ params: Promise.resolve({ id: "s1" }) });
    expect(redirect).toHaveBeenCalledWith("/sources/s1/read?panel=ask");
  });

  it("redirects the teach route into the reader teach panel", async () => {
    await TeachPage({ params: Promise.resolve({ id: "s1" }) });
    expect(redirect).toHaveBeenCalledWith("/sources/s1/read?panel=teach");
  });

  it("carries the dynamic source id through into the redirect target", async () => {
    await AskPage({ params: Promise.resolve({ id: "other-book" }) });
    expect(redirect).toHaveBeenCalledWith(
      "/sources/other-book/read?panel=ask",
    );
  });
});
