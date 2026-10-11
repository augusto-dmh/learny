// @vitest-environment jsdom

/**
 * A real surface never shows the backend's `detail`.
 *
 * In pt-BR, the library's source list failing with a `500` whose `detail` is an
 * English sentence shows the Portuguese server message — the English text the
 * backend sent stays on the error as data and never reaches the screen.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { LibraryScreen } from "../app/components/library-screen";
import ptBR from "../messages/pt-BR.json";
import { setTestLocale } from "./setup-intl";

const DETAIL = "Database connection pool exhausted.";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("request failures on screen", () => {
  it("backend detail never reaches the learner", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/auth/me") {
          return jsonResponse(200, {
            id: "u1",
            email: "a@b.c",
            created_at: "now",
            csrf_token: "csrf-xyz",
          });
        }
        if (url === "/api/sources") {
          return jsonResponse(500, { detail: DETAIL });
        }
        throw new Error(`unexpected fetch: ${url}`);
      }),
    );

    render(<LibraryScreen />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(ptBR.errors.status.server);
    expect(document.body.textContent).not.toContain(DETAIL);
  });
});
