// @vitest-environment jsdom

/**
 * The account panel's "AI profile" section is honest about choice and failure:
 * it exists only when the deployment offers at least one selectable profile
 * (absent — not a disabled shell — otherwise), the visible selection follows the
 * stored choice but renders the operator default when that choice is absent
 * from the catalog (never a phantom), persisting is confirmed-then-moved (a
 * failed save changes nothing on screen and surfaces the backend's own copy),
 * and a failed section load degrades to absence without breaking the rest of
 * the panel.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountPanel } from "../app/components/AccountPanel";

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`; fail loudly on anything unexpected. */
function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
  ai_profile_id: null,
});

const catalog = [
  {
    id: "house-primary",
    display_name: "House standard",
    description: "Grounded answers with verified citations.",
    grounding: "verified-spans",
    ask_enabled: true,
    teach_enabled: true,
  },
  {
    id: "house-economy",
    display_name: "Economy",
    description: "",
    grounding: "prompt-cited",
    ask_enabled: true,
    teach_enabled: false,
  },
];

function defaultHandlers(overrides: Record<string, Handler> = {}) {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    "GET /api/ai/profiles": () => jsonResponse(200, catalog),
    "GET /api/me/ai-profile": () => jsonResponse(200, { profile_id: null }),
    ...overrides,
  };
}

/** Flush the post-fetch state updates once the routed calls have resolved. */
async function settle() {
  await act(async () => {});
}

function radio(label: string): HTMLInputElement {
  return screen.getByLabelText(label) as HTMLInputElement;
}

beforeEach(() => {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AccountPanel AI profile section", () => {
  it("does not exist in the DOM at all when the catalog is empty (absent, not disabled)", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/ai/profiles": () => jsonResponse(200, []),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    expect(screen.queryByRole("region", { name: "AI profile" })).toBeNull();
    expect(screen.queryByLabelText("Operator default (recommended)")).toBeNull();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    // The rest of the account panel is untouched by the empty catalog.
    expect(screen.getByRole("button", { name: "Log out" })).toBeTruthy();
  });

  it("degrades to section-absent when the catalog read fails, never an error wall", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/ai/profiles": () => new Response(null, { status: 401 }),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    expect(screen.queryByRole("region", { name: "AI profile" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("a@b.c")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Log out" })).toBeTruthy();
    // The degrade is attributable: the failure lands in the console instead of
    // vanishing behind an intentionally-empty-catalog look.
    expect(warn).toHaveBeenCalledWith(
      "ai-profile section unavailable:",
      expect.anything(),
    );
  });

  it("lists the operator default plus one honest row per catalog profile", async () => {
    vi.stubGlobal("fetch", routedFetch(defaultHandlers()));

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    const section = screen.getByRole("region", { name: "AI profile" });
    expect(section).toBeTruthy();

    // Nothing stored: the operator default entry is the selection.
    expect(radio("Operator default (recommended)").checked).toBe(true);
    expect(radio("House standard").checked).toBe(false);
    expect(radio("Economy").checked).toBe(false);

    // Honest copy per row: name, the description line when non-empty, and the
    // grounding/eligibility hints.
    expect(screen.getByText("Grounded answers with verified citations.")).toBeTruthy();
    expect(
      screen.getByText("Citations are verified against the book. Works in Ask and Teach."),
    ).toBeTruthy();
    expect(
      screen.getByText("Citations are model-claimed and may be less precise. Works in Ask only."),
    ).toBeTruthy();
    // The second profile's description is empty: no phantom copy line for it.
    expect(screen.getAllByText("Economy")).toHaveLength(1);
  });

  it("reflects the stored choice read from the choice endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/me/ai-profile": () =>
            jsonResponse(200, { profile_id: "house-economy" }),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    expect(radio("Economy").checked).toBe(true);
    expect(radio("Operator default (recommended)").checked).toBe(false);
    expect(radio("House standard").checked).toBe(false);
  });

  it("renders a stale stored id as the operator default, never a phantom selection", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/me/ai-profile": () =>
            jsonResponse(200, { profile_id: "removed-tier" }),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    // The default entry is selected; the stale id appears nowhere.
    expect(radio("Operator default (recommended)").checked).toBe(true);
    expect(screen.queryByLabelText("removed-tier")).toBeNull();
    expect(screen.queryByText("removed-tier")).toBeNull();
    // Exactly the default row plus one row per catalog entry.
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("choosing a profile persists via PUT with the CSRF token, then moves the selection", async () => {
    const fetchMock = routedFetch(
      defaultHandlers({
        "PUT /api/me/ai-profile": () =>
          jsonResponse(200, { profile_id: "house-economy" }),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    fireEvent.click(radio("Economy"));

    await waitFor(() => expect(radio("Economy").checked).toBe(true));
    expect(radio("Operator default (recommended)").checked).toBe(false);

    const put = fetchMock.mock.calls.find(
      (c) => c[0] === "/api/me/ai-profile" && (c[1] as RequestInit).method === "PUT",
    );
    expect(put).toBeDefined();
    const init = put![1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ profile_id: "house-economy" });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(init.credentials).toBe("same-origin");
  });

  it("a failed PUT changes nothing visible and surfaces the backend's honest copy", async () => {
    const detail =
      "generation profile 'house-primary' is not declared by this deployment; " +
      "choose an id from GET /api/ai/profiles";
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/me/ai-profile": () =>
            jsonResponse(200, { profile_id: "house-economy" }),
          "PUT /api/me/ai-profile": () => jsonResponse(422, { detail }),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();
    expect(radio("Economy").checked).toBe(true);

    fireEvent.click(radio("House standard"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(detail);
    // The visible selection did not move on the failed save.
    expect(radio("Economy").checked).toBe(true);
    expect(radio("House standard").checked).toBe(false);
  });

  it("choosing the default entry persists via DELETE and reselects the default", async () => {
    const fetchMock = routedFetch(
      defaultHandlers({
        "GET /api/me/ai-profile": () =>
          jsonResponse(200, { profile_id: "house-economy" }),
        "DELETE /api/me/ai-profile": () => new Response(null, { status: 204 }),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();
    expect(radio("Economy").checked).toBe(true);

    fireEvent.click(radio("Operator default (recommended)"));

    await waitFor(() => expect(radio("Operator default (recommended)").checked).toBe(true));
    expect(radio("Economy").checked).toBe(false);

    const del = fetchMock.mock.calls.find(
      (c) => c[0] === "/api/me/ai-profile" && (c[1] as RequestInit).method === "DELETE",
    );
    expect(del).toBeDefined();
    expect(new Headers((del![1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
      "csrf-xyz",
    );
  });

  it("a failed reset also leaves the selection alone and shows the backend copy", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        defaultHandlers({
          "GET /api/me/ai-profile": () =>
            jsonResponse(200, { profile_id: "house-economy" }),
          "DELETE /api/me/ai-profile": () =>
            jsonResponse(500, { detail: "Could not reset your AI profile choice." }),
        }),
      ),
    );

    render(<AccountPanel />);
    await screen.findByText("a@b.c");
    await settle();

    fireEvent.click(radio("Operator default (recommended)"));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(radio("Economy").checked).toBe(true);
    expect(radio("Operator default (recommended)").checked).toBe(false);
  });
});
