// @vitest-environment jsdom

/**
 * The "Your own AI keys" section's hosted-policy half: each offered provider
 * row carries its privacy badge — Gemini's warns that unpaid-tier content may
 * improve Google's products, Anthropic's and OpenAI's state that API content
 * is not used for training; on an instance declared hosted the section adds
 * the hosted disclosure and a self-host keeps today's disclosure only; and the
 * month-to-date usage line beside the soft monthly budget control updates
 * from the budget PUT's response after every change.
 *
 * The base key rows, save/test/delete behavior live in
 * `tests/account-provider-keys.test.tsx` through the whole account panel;
 * this file renders the section directly to keep the hosted-policy states
 * enumerable in one place.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderKeysSection } from "../app/components/provider-keys-section";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

type Handler = (init: RequestInit) => Promise<Response> | Response;

const LIST_URL = "/api/me/provider-keys";
const BUDGET_URL = "/api/me/provider-keys/budget";

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
  powers: [{ profile_id: "byok-claude", display_name: "Your Claude", ask: true, teach: true }],
  powers_cards: true,
};
const openaiRow = {
  provider: "openai",
  label: "OpenAI",
  configured: false,
  last4: null,
  added_at: null,
  powers: [],
  powers_cards: false,
};
const geminiRow = {
  provider: "gemini",
  label: "Google Gemini",
  configured: false,
  last4: null,
  added_at: null,
  powers: [],
  powers_cards: false,
};

/** A quiet month with no budget, unless the test overrides the usage row. */
function usageRow(overrides: Record<string, unknown> = {}) {
  return {
    period: "2026-10",
    input_tokens: 115_000,
    output_tokens: 53_000,
    cost_usd_micros: 221_000,
    budget_usd_micros: null,
    ...overrides,
  };
}

function listBody(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    hosted: false,
    providers: [anthropicRow, openaiRow, geminiRow],
    usage: usageRow(),
    ...overrides,
  };
}

const HEADING = { en: "Your own AI keys", "pt-BR": "Suas próprias chaves de IA" } as const;

async function renderSection(
  fetchMock: ReturnType<typeof routedFetch>,
  locale: keyof typeof HEADING = "en",
) {
  vi.stubGlobal("fetch", fetchMock);
  render(<ProviderKeysSection csrfToken="csrf-xyz" />);
  // The section renders after the list resolves; the heading is its marker.
  await screen.findByRole("heading", { name: HEADING[locale] });
  await act(async () => {});
}

function row(provider: string): HTMLElement {
  const item = document.querySelector<HTMLElement>(`li[data-provider="${provider}"]`);
  if (!item) throw new Error(`no row for ${provider}`);
  return item;
}

const BUDGET_LABEL = { en: "Your usage and budget", "pt-BR": "Seu uso e limite" } as const;

function budgetBlock(locale: keyof typeof BUDGET_LABEL = "en"): HTMLElement {
  const block = document.querySelector<HTMLElement>(
    `[role="group"][aria-label="${BUDGET_LABEL[locale]}"]`,
  );
  if (!block) throw new Error("no usage and budget block");
  return block;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("provider keys section: privacy badges", () => {
  it("badge: each provider row shows what its provider does with the content", async () => {
    await renderSection(routedFetch({ [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()) }));

    expect(within(row("gemini")).getByText(/unpaid-tier Gemini key/i).textContent).toBe(
      "Google may use content sent with an unpaid-tier Gemini key to improve its products.",
    );
    expect(within(row("anthropic")).getByText(/Anthropic does not use content/i).textContent).toBe(
      "Anthropic does not use content sent over its API to train its models.",
    );
    expect(within(row("openai")).getByText(/OpenAI does not use content/i).textContent).toBe(
      "OpenAI does not use content sent over its API to train its models.",
    );
  });

  it("badge: the badges render in Brazilian Portuguese", async () => {
    setTestLocale("pt-BR");
    await renderSection(
      routedFetch({ [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()) }),
      "pt-BR",
    );

    expect(within(row("gemini")).getByText(/não pago/i).textContent).toBe(
      "A Google pode usar o conteúdo enviado com uma chave Gemini do nível não pago para melhorar os seus produtos.",
    );
    expect(within(row("anthropic")).getByText(/não treina|não usa/i).textContent).toBe(
      "A Anthropic não usa o conteúdo enviado pela API para treinar os seus modelos.",
    );
  });
});

describe("provider keys section: hosted disclosure", () => {
  it("disclosure: a hosted instance shows the hosted disclosure beside today's", async () => {
    await renderSection(
      routedFetch({ [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody({ hosted: true })) }),
    );

    expect(
      screen.getByText(
        "This is a hosted Learny: your key is stored encrypted on this server — not on your computer — every call still runs under your own agreement with the provider, and there are no custom endpoints here: your key is sent only to the provider itself.",
      ),
    ).toBeTruthy();
    // Today's disclosure stays: the provider bills the learner either way.
    expect(
      screen.getByText(
        "Calls made with your key are billed by that provider to you, under your own agreement with them. Learny stores your key encrypted and can never show it again.",
      ),
    ).toBeTruthy();
  });

  it("disclosure: a self-host keeps today's disclosure only", async () => {
    await renderSection(routedFetch({ [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()) }));

    expect(
      screen.getByText(
        "Calls made with your key are billed by that provider to you, under your own agreement with them. Learny stores your key encrypted and can never show it again.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/hosted Learny/)).toBeNull();
  });
});

describe("provider keys section: usage and budget", () => {
  it("usage: the month-to-date line shows the estimated cost, the tokens and the budget", async () => {
    await renderSection(
      routedFetch({
        [`GET ${LIST_URL}`]: () =>
          jsonResponse(
            200,
            listBody({
              usage: usageRow({ budget_usd_micros: 5_000_000 }),
            }),
          ),
      }),
    );

    const block = budgetBlock();
    // 221000 micros is $0.221; the tokens group by the locale; the budget reads
    // as money the learner set, from the same formatter.
    expect(block.textContent).toContain("This month on your own keys: about $0.221");
    expect(block.textContent).toContain("115,000 input tokens");
    expect(block.textContent).toContain("53,000 output tokens");
    expect(block.textContent).toContain("Your monthly budget is $5.");
  });

  it("usage: a quiet month with no budget reads as no budget set", async () => {
    await renderSection(routedFetch({ [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()) }));

    expect(budgetBlock().textContent).toContain("No monthly budget is set.");
  });

  it("usage: saving a budget updates the line from the PUT's response", async () => {
    const fetchMock = routedFetch({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()),
      [`PUT ${BUDGET_URL}`]: (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ monthly_budget_usd: 7 });
        expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-xyz");
        return jsonResponse(200, usageRow({ budget_usd_micros: 7_000_000 }));
      },
    });
    await renderSection(fetchMock);

    fireEvent.change(screen.getByLabelText("Monthly budget in US dollars"), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save budget" }));
    // The PUT's response is the refreshed view: the line reads the stored truth.
    await waitFor(() => expect(budgetBlock().textContent).toContain("Your monthly budget is $7."));
    expect(budgetBlock().textContent).not.toContain("No monthly budget is set.");
  });

  it("usage: clearing the budget sends null and the line reads no budget", async () => {
    const fetchMock = routedFetch({
      [`GET ${LIST_URL}`]: () =>
        jsonResponse(200, listBody({ usage: usageRow({ budget_usd_micros: 5_000_000 }) })),
      [`PUT ${BUDGET_URL}`]: (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ monthly_budget_usd: null });
        return jsonResponse(200, usageRow());
      },
    });
    await renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Clear budget" }));
    await waitFor(() => expect(budgetBlock().textContent).toContain("No monthly budget is set."));
  });

  it("usage: an out-of-range budget shows the catalog copy and sends nothing", async () => {
    const fetchMock = routedFetch({
      [`GET ${LIST_URL}`]: () => jsonResponse(200, listBody()),
    });
    await renderSection(fetchMock);

    for (const bad of ["0", "-3", "20000", "abc"]) {
      fireEvent.change(screen.getByLabelText("Monthly budget in US dollars"), {
        target: { value: bad },
      });
      fireEvent.click(screen.getByRole("button", { name: "Save budget" }));
      expect(
        await screen.findByText(
          "Enter a dollar amount above 0 and at most 10,000, or clear the budget.",
        ),
      ).toBeTruthy();
    }
    expect(fetchMock.mock.calls.filter(([url]) => url === BUDGET_URL)).toHaveLength(0);
  });

  it("usage: a failed save shows the operation's copy and keeps the stored budget", async () => {
    const fetchMock = routedFetch({
      [`GET ${LIST_URL}`]: () =>
        jsonResponse(200, listBody({ usage: usageRow({ budget_usd_micros: 5_000_000 }) })),
      [`PUT ${BUDGET_URL}`]: () => jsonResponse(500, { detail: "boom" }),
    });
    await renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Clear budget" }));
    expect(
      await screen.findByText("The server had a problem. Please try again."),
    ).toBeTruthy();
    // Nothing optimistic: the line keeps reading the stored budget.
    expect(budgetBlock().textContent).toContain("Your monthly budget is $5.");
  });

  it("usage renders in Brazilian Portuguese", async () => {
    setTestLocale("pt-BR");
    await renderSection(
      routedFetch({
        [`GET ${LIST_URL}`]: () =>
          jsonResponse(
            200,
            listBody({
              usage: usageRow({ budget_usd_micros: 5_000_000 }),
            }),
          ),
      }),
      "pt-BR",
    );

    const block = budgetBlock("pt-BR");
    expect(block.textContent).toContain("Neste mês nas suas próprias chaves: cerca de US$");
    expect(block.textContent).toContain("115.000 tokens de entrada");
    expect(block.textContent).toContain("53.000 tokens de saída");
    expect(block.textContent).toContain("O seu limite mensal é US$");
    // The pt-BR render probe: no English copy leaks into the block.
    expectNoEnglishCopy(block.textContent ?? "", "account");
  });
});
