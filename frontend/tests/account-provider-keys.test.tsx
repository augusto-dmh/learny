// @vitest-environment jsdom

/**
 * The account panel's "Your own AI keys" section: it exists only when the
 * instance offers learner keys, shows what each key powers, never renders a key
 * after it is saved, reports a test outcome in plain words, asks before
 * deleting, keeps the previous state on any failure, and tells the learner who
 * bills the calls and that the key cannot be shown again.
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountPanel } from "../app/components/AccountPanel";
import { setTestLocale } from "./setup-intl";

type Handler = (init: RequestInit) => Promise<Response> | Response;

const KEY = "sk-proj-typed-into-the-input-0123456789";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Route `fetch` by `"<METHOD> <url>"`, recording every call; fail on anything unexpected. */
function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const anthropicRow = {
  provider: "anthropic",
  label: "Anthropic",
  configured: true,
  last4: "a1B2",
  added_at: "2026-10-01T12:00:00Z",
  powers: [
    { profile_id: "byok-claude", display_name: "Your Claude", ask: true, teach: true },
    { profile_id: "byok-haiku", display_name: "Quick Claude", ask: true, teach: false },
  ],
  powers_cards: true,
};
const openaiRow = {
  provider: "openai",
  label: "OpenAI",
  configured: false,
  last4: null,
  added_at: null,
  powers: [{ profile_id: "byok-gpt", display_name: "Your GPT", ask: true, teach: false }],
  powers_cards: false,
};
const savedOpenai = {
  ...openaiRow,
  configured: true,
  last4: "6789",
  added_at: "2026-10-11T09:00:00Z",
};

function handlers(overrides: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    "GET /api/auth/me": () =>
      jsonResponse(200, {
        id: "u1",
        email: "a@b.c",
        created_at: "now",
        csrf_token: "csrf-xyz",
        locale: null,
      }),
    "GET /api/ai/profiles": () => jsonResponse(200, []),
    "GET /api/me/ai-profile": () => jsonResponse(200, { profile_id: null }),
    "GET /api/me/provider-keys": () =>
      jsonResponse(200, { enabled: true, providers: [anthropicRow, openaiRow] }),
    ...overrides,
  };
}

async function renderPanel(fetchMock: ReturnType<typeof routedFetch>) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AccountPanel />);
  await screen.findByText("a@b.c");
  await act(async () => {});
}

function row(provider: string): HTMLElement {
  const item = document.querySelector<HTMLElement>(`li[data-provider="${provider}"]`);
  if (!item) throw new Error(`no row for ${provider}`);
  return item;
}

function calls(fetchMock: ReturnType<typeof routedFetch>, method: string, url: string) {
  return fetchMock.mock.calls.filter(
    ([callUrl, init]) => callUrl === url && (init?.method ?? "GET") === method,
  );
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
  vi.unstubAllGlobals();
});

describe("AccountPanel provider keys section", () => {
  it("is hidden when disabled", async () => {
    await renderPanel(
      routedFetch(
        handlers({
          "GET /api/me/provider-keys": () => jsonResponse(200, { enabled: false, providers: [] }),
        }),
      ),
    );

    expect(screen.queryByRole("heading", { name: "Your own AI keys" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Your own AI keys" })).toBeNull();
    expect(screen.getByRole("button", { name: "Log out" })).toBeTruthy();
  });

  it("renders configured and unconfigured rows", async () => {
    await renderPanel(routedFetch(handlers()));

    expect(screen.getByRole("heading", { name: "Your own AI keys" })).toBeTruthy();
    const anthropic = within(row("anthropic"));
    expect(anthropic.getByText("•••• a1B2")).toBeTruthy();
    expect(anthropic.getByText("Added Oct 1, 2026")).toBeTruthy();
    expect(anthropic.getByText("Your Claude: Ask and Teach")).toBeTruthy();
    expect(anthropic.getByText("Quick Claude: Ask only")).toBeTruthy();
    expect(anthropic.getByText("Flashcards & decks")).toBeTruthy();
    expect(anthropic.queryByLabelText("API key for Anthropic")).toBeNull();

    const openai = within(row("openai"));
    const input = openai.getByLabelText("API key for OpenAI") as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(openai.getByRole("button", { name: "Save key" })).toBeTruthy();
    expect(openai.getByText("Your GPT: Ask only")).toBeTruthy();
    expect(openai.queryByText("Flashcards & decks")).toBeNull();
  });

  it("save clears and never re-renders the key", async () => {
    const fetchMock = routedFetch(
      handlers({ "PUT /api/me/provider-keys/openai": () => jsonResponse(200, savedOpenai) }),
    );
    await renderPanel(fetchMock);

    const input = within(row("openai")).getByLabelText("API key for OpenAI") as HTMLInputElement;
    fireEvent.change(input, { target: { value: KEY } });
    fireEvent.click(within(row("openai")).getByRole("button", { name: "Save key" }));
    await within(row("openai")).findByText("•••• 6789");

    const [[, init]] = calls(fetchMock, "PUT", "/api/me/provider-keys/openai");
    expect(JSON.parse(String(init?.body))).toEqual({ api_key: KEY });
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-xyz");
    expect(within(row("openai")).queryByLabelText("API key for OpenAI")).toBeNull();
    expect(document.body.textContent).not.toContain(KEY);
    expect(document.body.innerHTML).not.toContain(KEY.slice(-12));
    for (const element of document.querySelectorAll("input")) {
      expect(element.value).not.toContain(KEY.slice(-12));
    }

    // Opening the input again (Replace) starts empty: the saved key is gone
    // from the component, not merely hidden.
    fireEvent.click(within(row("openai")).getByRole("button", { name: "Replace key" }));
    const reopened = within(row("openai")).getByLabelText("API key for OpenAI") as HTMLInputElement;
    expect(reopened.value).toBe("");
  });

  it("test outcome messages", async () => {
    const outcomes = [
      { ok: true, reason: null },
      { ok: false, reason: "rejected" },
      { ok: false, reason: "rate_limited" },
      { ok: false, reason: "unavailable" },
    ];
    let next = 0;
    await renderPanel(
      routedFetch(
        handlers({
          "POST /api/me/provider-keys/anthropic/test": () => jsonResponse(200, outcomes[next++]),
        }),
      ),
    );

    const seen: string[] = [];
    for (let i = 0; i < outcomes.length; i++) {
      fireEvent.click(within(row("anthropic")).getByRole("button", { name: "Test key" }));
      const status = await within(row("anthropic")).findByRole("status");
      seen.push(status.textContent ?? "");
    }

    expect(seen[0]).toBe("Key works");
    expect(seen.slice(1)).toEqual([
      "The provider rejected this key. Check it, then save it again.",
      "The provider is limiting requests on this key right now. Try again in a moment.",
      "The provider could not be reached. Try again later.",
    ]);
    expect(new Set(seen).size).toBe(4);
  });

  it("delete confirms first", async () => {
    const fetchMock = routedFetch(
      handlers({ "DELETE /api/me/provider-keys/anthropic": () => new Response(null, { status: 204 }) }),
    );
    await renderPanel(fetchMock);
    const anthropic = within(row("anthropic"));

    fireEvent.click(anthropic.getByRole("button", { name: "Delete key" }));
    expect(
      anthropic.getByText("Delete your Anthropic key? Your requests go back to Learny's own AI."),
    ).toBeTruthy();
    fireEvent.click(anthropic.getByRole("button", { name: "Cancel" }));
    await act(async () => {});
    expect(calls(fetchMock, "DELETE", "/api/me/provider-keys/anthropic")).toHaveLength(0);
    expect(anthropic.getByText("•••• a1B2")).toBeTruthy();

    fireEvent.click(anthropic.getByRole("button", { name: "Delete key" }));
    expect(calls(fetchMock, "DELETE", "/api/me/provider-keys/anthropic")).toHaveLength(0);
    fireEvent.click(anthropic.getByRole("button", { name: "Yes, delete it" }));
    await anthropic.findByLabelText("API key for Anthropic");

    expect(calls(fetchMock, "DELETE", "/api/me/provider-keys/anthropic")).toHaveLength(1);
    expect(anthropic.queryByText("•••• a1B2")).toBeNull();
    expect(anthropic.getByText("No key saved.")).toBeTruthy();
  });

  it("failure keeps state and shows error", async () => {
    await renderPanel(
      routedFetch(
        handlers({
          "PUT /api/me/provider-keys/openai": () => jsonResponse(422, { detail: "bad key" }),
          "POST /api/me/provider-keys/anthropic/test": () => new Response(null, { status: 503 }),
          "DELETE /api/me/provider-keys/anthropic": () => jsonResponse(404, { detail: "gone" }),
        }),
      ),
    );

    const openai = within(row("openai"));
    fireEvent.change(openai.getByLabelText("API key for OpenAI"), { target: { value: KEY } });
    fireEvent.click(openai.getByRole("button", { name: "Save key" }));
    expect((await openai.findByRole("alert")).textContent).toBe("Could not save your key.");
    expect(openai.getByText("No key saved.")).toBeTruthy();
    expect(openai.queryByText(/••••/)).toBeNull();

    const anthropic = within(row("anthropic"));
    fireEvent.click(anthropic.getByRole("button", { name: "Test key" }));
    expect((await anthropic.findByRole("alert")).textContent).toBe(
      "The server had a problem. Please try again.",
    );
    expect(anthropic.queryByRole("status")).toBeNull();

    fireEvent.click(anthropic.getByRole("button", { name: "Delete key" }));
    fireEvent.click(anthropic.getByRole("button", { name: "Yes, delete it" }));
    await act(async () => {});
    expect(anthropic.getByRole("alert").textContent).toBe("Could not delete your key.");
    expect(anthropic.getByText("•••• a1B2")).toBeTruthy();
  });

  it("disclosure copy", async () => {
    await renderPanel(routedFetch(handlers()));

    expect(
      screen.getByText(
        "Calls made with your key are billed by that provider to you, under your own agreement with them. Learny stores your key encrypted and can never show it again.",
      ),
    ).toBeTruthy();
  });

  it("renders in Brazilian Portuguese", async () => {
    setTestLocale("pt-BR");
    await renderPanel(routedFetch(handlers()));

    expect(screen.getByRole("heading", { name: "Suas próprias chaves de IA" })).toBeTruthy();
    expect(within(row("anthropic")).getByText("Flashcards e baralhos")).toBeTruthy();
    expect(within(row("anthropic")).getByText("Your Claude: Perguntar e Ensinar")).toBeTruthy();
    expect(within(row("openai")).getByLabelText("Chave de API do provedor OpenAI")).toBeTruthy();
    expect(screen.getByText(/cobradas pelo provedor diretamente de você/)).toBeTruthy();
  });
});
