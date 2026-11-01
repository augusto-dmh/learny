// @vitest-environment jsdom

/**
 * The per-answer usage line (S4, C19): an answer whose adapter reported usage
 * renders exactly one usage line in the Chat surface — the input and output
 * token counts always, and for a learner-keyed answer the estimated cost
 * labeled as on the learner's own key — in both catalogs; a house-served
 * answer shows the tokens without a cost, and an answer with no reported
 * usage shows no usage line at all.
 *
 * Both paths the line reaches are covered: the live stream's terminal
 * `data-answer-usage` part (AskPanel streaming) and the restored history's
 * replayed usage fields (a conversation re-read from the server). The Teach
 * surface renders the same shared component through its own wiring; that
 * wiring is proven in `tests/teach-panel.test.tsx`.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { AskPanel } from "../app/components/ask-panel";
import { writeActiveConversation } from "../app/lib/active-conversation";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

// AI Elements' Conversation (stick-to-bottom) reaches for ResizeObserver and
// pointer-capture APIs jsdom lacks; stub them as the ask-panel tests do.
beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
});

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
    if (!handler && /^GET \/api\/sources\/[^/?]+$/.test(key)) {
      return jsonResponse(200, {
        id: "s1",
        title: "Ready Book",
        filename: "s1.epub",
        byte_size: 3,
        content_type: "application/epub+zip",
        status: "ready",
        created_at: "now",
        is_sample: false,
        suggested_question: null,
      });
    }
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

/** A UI Message Stream v1 SSE response whose frames the test pushes on demand. */
function sseStream() {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const response = new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
  // Enqueue one frame, then wait out the stream throttle inside `act` so the
  // SDK's trailing flush lands and renders before the next assertion.
  const frame = (bytes: Uint8Array) =>
    act(async () => {
      controller.enqueue(bytes);
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
  return {
    response,
    push: (obj: unknown) => frame(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`)),
    done: () => frame(encoder.encode("data: [DONE]\n\n")).then(() => controller.close()),
  };
}

const CREATE_URL = "/api/conversations";
const STREAM_URL = "/api/conversations/conv1/turns/stream";
const RESTORE_URL = "/api/conversations/conv1";

const conversation = {
  id: "conv1",
  source_id: "s1",
  title: "Untitled conversation",
  scope_anchors: [],
  include_notes: false,
  created_at: "now",
  updated_at: "now",
};

function baseHandlers(
  stream: () => Response,
  extra: Record<string, Handler> = {},
): Record<string, Handler> {
  return {
    [`POST ${CREATE_URL}`]: () => jsonResponse(201, conversation),
    [`POST ${STREAM_URL}`]: () => stream(),
    ...extra,
  };
}

/** The terminal frames of an answered turn, with the caller's usage frames. */
async function streamAnswer(
  stream: ReturnType<typeof sseStream>,
  usage: Record<string, unknown> | null,
): Promise<void> {
  await stream.push({ type: "start", messageId: "m1" });
  await stream.push({ type: "text-start", id: "t1" });
  await stream.push({
    type: "text-delta",
    id: "t1",
    delta: "Ada Lovelace wrote the first algorithm.",
  });
  await stream.push({ type: "text-end", id: "t1" });
  await stream.push({
    type: "data-answer-status",
    data: { status: "answered" },
  });
  if (usage !== null) {
    await stream.push({ type: "data-answer-usage", data: usage });
  }
  await stream.push({ type: "finish" });
  await stream.done();
}

function callsTo(
  fetchMock: ReturnType<typeof routedFetch>,
  url: string,
): unknown[][] {
  return fetchMock.mock.calls.filter(([called]) => called === url);
}

/** The input's placeholder and the submit label, per locale the tests render. */
const INPUT = {
  en: { placeholder: /ask a question/i, submit: "Submit" },
  "pt-BR": { placeholder: /faça uma pergunta/i, submit: "Enviar" },
} as const;

async function ask(value: string, locale: keyof typeof INPUT = "en") {
  fireEvent.change(await screen.findByPlaceholderText(INPUT[locale].placeholder), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: INPUT[locale].submit }));
}

function usageLine(): HTMLElement {
  const line = document.querySelector<HTMLElement>('[data-testid="answer-usage"]');
  if (!line) throw new Error("no usage line rendered");
  return line;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("answer usage line", () => {
  it("usage line: a learner-keyed answer renders the tokens and the estimated cost on the learner's own key", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Who wrote the first algorithm?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    // 1000 input at 3 USD/M + 500 output at 15 USD/M is 10500 micros — the
    // same estimate the backend stamps on the turn (C18).
    await streamAnswer(stream, {
      input_tokens: 1000,
      output_tokens: 500,
      cost_usd_micros: 10500,
      user_keyed: true,
    });
    await waitFor(() => expect(document.body.textContent).toContain("Ada Lovelace"));

    // One line, carrying both token counts and the cost labeled as the
    // learner's own spend.
    expect(screen.getAllByTestId("answer-usage")).toHaveLength(1);
    expect(usageLine().textContent).toBe(
      "1,000 input tokens · 500 output tokens · about $0.0105 on your own key",
    );
  });

  it("usage line: a house-served answer renders the tokens without a cost", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Who wrote the first algorithm?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    await streamAnswer(stream, {
      input_tokens: 1000,
      output_tokens: 500,
      cost_usd_micros: null,
      user_keyed: false,
    });
    await waitFor(() => expect(document.body.textContent).toContain("Ada Lovelace"));

    // The house paid: tokens yes, money never — pricing it would imply the
    // learner was billed.
    expect(usageLine().textContent).toBe("1,000 input tokens · 500 output tokens");
    expect(usageLine().textContent).not.toContain("$");
    expect(usageLine().textContent).not.toContain("own key");
  });

  it("usage line: an answer with no reported usage renders no usage line", async () => {
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Who wrote the first algorithm?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    // The deterministic local adapter reports nothing: the backend sends no
    // usage part, and nothing renders — not a zero.
    await streamAnswer(stream, null);
    await waitFor(() => expect(document.body.textContent).toContain("Ada Lovelace"));

    expect(screen.queryByTestId("answer-usage")).toBeNull();
  });

  it("usage line: a restored learner-keyed answer renders the same line from its stored usage", async () => {
    const restored = {
      ...conversation,
      turns: [
        {
          turn_index: 0,
          message: "Who wrote the first algorithm?",
          mode: "answer",
          answer_status: "answered",
          text: "Ada Lovelace wrote the first algorithm.",
          citations: [],
          evidence_count: 0,
          model: "claude-byok",
          created_at: "now",
          usage_input_tokens: 1000,
          usage_output_tokens: 500,
          cost_usd_micros: 10500,
          user_keyed: true,
        },
      ],
    };
    writeActiveConversation("s1", "ask", "conv1");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`GET ${RESTORE_URL}`]: () => jsonResponse(200, restored),
      }),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    await screen.findByText(/Ada Lovelace wrote the first algorithm\./);
    expect(usageLine().textContent).toBe(
      "1,000 input tokens · 500 output tokens · about $0.0105 on your own key",
    );
  });

  it("usage line: a restored answer stored before the usage columns renders no line", async () => {
    const restored = {
      ...conversation,
      turns: [
        {
          turn_index: 0,
          message: "Who wrote the first algorithm?",
          mode: "answer",
          answer_status: "answered",
          text: "Ada Lovelace wrote the first algorithm.",
          citations: [],
          evidence_count: 0,
          model: "local-extractive",
          created_at: "now",
        },
      ],
    };
    writeActiveConversation("s1", "ask", "conv1");
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [`GET ${RESTORE_URL}`]: () => jsonResponse(200, restored),
      }),
    );

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);

    await screen.findByText(/Ada Lovelace wrote the first algorithm\./);
    expect(screen.queryByTestId("answer-usage")).toBeNull();
  });

  it("usage line renders in Brazilian Portuguese", async () => {
    setTestLocale("pt-BR");
    const stream = sseStream();
    const fetchMock = routedFetch(baseHandlers(() => stream.response));
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Quem escreveu o primeiro algoritmo?", "pt-BR");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    await streamAnswer(stream, {
      input_tokens: 1000,
      output_tokens: 500,
      cost_usd_micros: 10500,
      user_keyed: true,
    });
    await waitFor(() => expect(document.body.textContent).toContain("Ada Lovelace"));

    // Intl separates the US$ symbol from the amount with a non-breaking space.
    expect(usageLine().textContent).toBe(
      "1.000 tokens de entrada · 500 tokens de saída · cerca de US$\u00A00,0105 na sua própria chave",
    );
    // The pt-BR render probe: no English copy leaks into the line.
    expectNoEnglishCopy(usageLine().textContent ?? "", "chat");
  });
});

describe("typed own-budget refusals", () => {
  /**
   * A stream start answered with one of the backend's typed 429 refusals
   * (`{"detail", "code"}`); the learner reads catalog copy keyed off the code,
   * never the backend's English `detail`.
   */
  function refused(status: number, code: string): Handler {
    return () =>
      jsonResponse(status, {
        detail: `BACKEND-ENGLISH-DETAIL for ${code}`,
        code,
      });
  }

  it("budget refusal: a turn refused by the learner's own monthly budget says so and names Account", async () => {
    const fetchMock = routedFetch(
      baseHandlers(() => jsonResponse(500, {}), {
        [`POST ${STREAM_URL}`]: refused(429, "byok_budget"),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Who wrote the first algorithm?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    // The copy is the catalog's, keyed off the machine code: it names the
    // learner's own monthly budget and where to change it.
    // The failure renders in-thread and as the banner; both carry the copy.
    expect(
      (await screen.findAllByText(
        "Your own monthly budget for AI keys has been reached, so your own keys pause. Raise or clear the budget in Account to continue.",
      )).length,
    ).toBeGreaterThan(0);
    // The backend `detail` is data for logs, never rendered copy.
    expect(document.body.textContent).not.toContain("BACKEND-ENGLISH-DETAIL");
  });

  it("budget refusal: the per-book ceiling copy names the monthly per-book limit", async () => {
    const fetchMock = routedFetch(
      baseHandlers(() => jsonResponse(500, {}), {
        [`POST ${STREAM_URL}`]: refused(429, "byok_corpus_limit"),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Who wrote the first algorithm?");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    expect(
      (await screen.findAllByText(
        "This book has reached its monthly limit of prompt tokens on your own key. Try again next month, or ask Learny's own AI instead.",
      )).length,
    ).toBeGreaterThan(0);
  });

  it("budget refusal copy renders in Brazilian Portuguese", async () => {
    setTestLocale("pt-BR");
    const fetchMock = routedFetch(
      baseHandlers(() => jsonResponse(500, {}), {
        [`POST ${STREAM_URL}`]: refused(429, "byok_budget"),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AskPanel sourceId="s1" csrf="csrf-xyz" />);
    await ask("Quem escreveu o primeiro algoritmo?", "pt-BR");
    await waitFor(() => expect(callsTo(fetchMock, STREAM_URL)).toHaveLength(1));

    expect(
      (await screen.findAllByText(
        "O seu próprio limite mensal para as chaves de IA foi atingido, então as suas chaves pausaram. Aumente ou remova o limite na Conta para continuar.",
      )).length,
    ).toBeGreaterThan(0);
  });
});
