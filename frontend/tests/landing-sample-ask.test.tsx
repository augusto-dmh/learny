// @vitest-environment jsdom

/**
 * The landing page's capped guest sample ask: a signed-out visitor sees the
 * shared-sample label and the cap note, submits the prefilled suggested
 * question, and reads the cited answer rendered like every Ask. The refusals
 * speak: an exhausted budget says so (never a silent degradation), a grounded
 * nothing says the sample has no passage, and a failed request reads the
 * operation copy — in both catalogs.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LandingPage from "../app/page";
import { setTestLocale } from "./setup-intl";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const GROUNDED = {
  found: true,
  answer: "Deception precedes every battle. [^1]",
  citations: [
    {
      chunk_id: "0f0d1a2b-3c4d-5e6f-8a9b-0c1d2e3f4a5b",
      source_id: "11111111-2222-3333-4444-555555555555",
      section_path: ["I. Laying Plans"],
      anchor: "sun-tzu#I.1",
      page_span: null,
      snippet: "All warfare is based on deception.",
      score: 1.0,
    },
  ],
  sample: true,
  model: "local-extractive",
};

afterEach(() => {
  cleanup();
  setTestLocale("en");
  vi.unstubAllGlobals();
});

function renderLanding() {
  render(<LandingPage />);
  fireEvent.submit(screen.getByRole("form", { name: "Ask the sample a question" }));
}

describe("the landing sample ask (en)", () => {
  it("offers the sample ask and labels the answer as the shared sample", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, GROUNDED));
    vi.stubGlobal("fetch", fetchMock);

    render(<LandingPage />);

    // The surface is labeled as the shared sample and carries the cap note.
    expect(screen.getByText(/no account needed/)).toBeTruthy();
    expect(screen.getByText("A few questions a day")).toBeTruthy();

    const input = screen.getByTestId("guest-ask-input") as HTMLTextAreaElement;
    // The suggested question rides as the placeholder, ready to be sent as-is.
    expect(input.placeholder).toContain("all warfare is based on deception");
    fireEvent.change(input, { target: { value: "What is warfare based on?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask the sample" }));

    await waitFor(() =>
      expect(screen.getByTestId("guest-ask-answer")).toBeTruthy(),
    );
    expect(document.body.textContent).toContain("Deception precedes every battle.");
    // The request went through the same-origin proxy with the typed question.
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sample/ask");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      question: "What is warfare based on?",
    });
  });

  it("the exhausted budget says so instead of degrading", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(429, { detail: "x" })));

    renderLanding();

    await waitFor(() =>
      expect(screen.getByTestId("guest-ask-error")).toBeTruthy(),
    );
    expect(screen.getByTestId("guest-ask-error").textContent).toContain(
      "reached today's limit",
    );
    expect(screen.queryByTestId("guest-ask-answer")).toBeNull();
  });

  it("a grounded nothing says the sample has no passage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(200, { ...GROUNDED, found: false, answer: null, citations: [] })),
    );

    renderLanding();

    await waitFor(() =>
      expect(screen.getByTestId("guest-ask-not-found")).toBeTruthy(),
    );
    expect(screen.getByTestId("guest-ask-not-found").textContent).toContain(
      "no passage that answers that",
    );
  });

  it("a failed request reads the shared server copy", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(502, { detail: "x" })));

    renderLanding();

    await waitFor(() =>
      expect(screen.getByTestId("guest-ask-error")).toBeTruthy(),
    );
    // A 5xx reads the status-class copy shared by every surface (the error
    // contract: the class wins over the operation); the sample-specific line
    // is reserved for the exhausted budget, which the visitor can act on.
    expect(screen.getByTestId("guest-ask-error").textContent).toContain(
      "The server had a problem. Please try again.",
    );
  });
});

describe("the landing sample ask (pt-BR)", () => {
  it("renders the label, the exhausted refusal, and the answer label in Portuguese", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(429, { detail: "x" })));

    render(<LandingPage />);
    expect(screen.getByText(/sem precisar de conta/)).toBeTruthy();

    fireEvent.submit(screen.getByRole("form", { name: "Pergunte à amostra" }));
    await waitFor(() =>
      expect(screen.getByTestId("guest-ask-error")).toBeTruthy(),
    );
    expect(screen.getByTestId("guest-ask-error").textContent).toContain(
      "atingiu o limite de hoje",
    );
  });
});
