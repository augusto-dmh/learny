// @vitest-environment jsdom

/**
 * The checkpoint dialog's step machine. What is visible, and what is sent,
 * at each step.
 *
 * `fetch` is routed by "<METHOD> <url>" and throws on anything unregistered, so
 * a request the step should not make fails the test instead of passing silently.
 * The order of the guarantees is the point: no request before a prediction, no
 * answer before a confidence-tagged response resolves, "Just explain" never the
 * primary action, and feedback that quotes rather than grades.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { CheckpointDialog } from "../app/components/checkpoint-dialog";

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

/** A promise whose resolution the test controls. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const START = "POST /api/sources/s1/checkpoints";
const SECRET = "Eighteen distinct operations";

const recallAndExplain = {
  checkpoint_id: "c1",
  section_title: "The Division of Labour",
  anchor: "ch1#s1",
  attempts: [
    { attempt_id: "a1", kind: "recall", question: "How many operations make a pin?" },
    {
      attempt_id: "a2",
      kind: "explain",
      question: 'Explain "The Division of Labour" in your own words.',
    },
  ],
};

const explainOnly = { ...recallAndExplain, attempts: [recallAndExplain.attempts[1]] };

const feedback = {
  feedback: "You captured the pin example. The passage also says this:",
  citations: [
    {
      anchor: "ch1#s1",
      section_path: ["Book I", "The Division of Labour"],
      quote: "Dexterity grows when each worker repeats a single operation.",
    },
  ],
};

function renderDialog(onClose = vi.fn()) {
  render(
    <CheckpointDialog
      open
      sourceId="s1"
      anchor="ch1#s1"
      sectionTitle="The Division of Labour"
      csrf="csrf-xyz"
      onClose={onClose}
    />,
  );
  return onClose;
}

function bodyOf(init: RequestInit): unknown {
  return JSON.parse(String(init.body));
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CheckpointDialog", () => {
  it("opens on the prediction step without calling the API", () => {
    const fetchMock = routedFetch({});
    vi.stubGlobal("fetch", fetchMock);

    renderDialog();

    for (const label of ["Little", "Some", "Most", "Skip"]) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["Little", 1],
    ["Some", 2],
    ["Most", 3],
    ["Skip", null],
  ])("prediction choices map to 1, 2, 3 and null (%s)", async (label, expected) => {
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [START]: (init) => {
          bodies.push(bodyOf(init));
          return jsonResponse(201, explainOnly);
        },
      }),
    );
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: label }));

    await screen.findByTestId("checkpoint-ask-explain");
    expect(bodies).toEqual([{ anchor: "ch1#s1", prediction: expected }]);
  });

  it("recall answer appears only after a confidence submit resolves", async () => {
    const response = deferred<Response>();
    const sent: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [START]: () => jsonResponse(201, recallAndExplain),
        "POST /api/checkpoint-attempts/a1/response": (init) => {
          sent.push(bodyOf(init));
          return response.promise;
        },
      }),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Some" }));
    await screen.findByText("How many operations make a pin?");

    expect(screen.queryByText(SECRET)).toBeNull();
    fireEvent.change(screen.getByRole("textbox", { name: "Your answer" }), {
      target: { value: "eighteen?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Fairly sure" }));
    await waitFor(() => expect(sent).toEqual([{ response: "eighteen?", confidence: 2 }]));
    // In flight: still no answer on screen.
    expect(screen.queryByText(SECRET)).toBeNull();

    response.resolve(
      jsonResponse(200, {
        answer: SECRET,
        source_excerpt: "Pin making is divided into about eighteen distinct operations.",
        anchor: "ch1#s1",
        section_path: ["Book I", "The Division of Labour"],
      }),
    );

    expect(await screen.findByText(SECRET)).toBeTruthy();
    for (const label of ["Again", "Hard", "Good", "Easy"]) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }
  });

  it("just explain is a secondary action on the explain step", async () => {
    const fetchMock = routedFetch({ [START]: () => jsonResponse(201, explainOnly) });
    vi.stubGlobal("fetch", fetchMock);
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    const step = await screen.findByTestId("checkpoint-ask-explain");

    const justExplain = within(step).getByRole("button", { name: "Just explain" });
    expect(justExplain.getAttribute("data-variant")).toBe("link");
    for (const label of ["Not sure", "Fairly sure", "Sure"]) {
      expect(within(step).getByRole("button", { name: label }).getAttribute("data-variant")).toBe(
        "default",
      );
    }
    expect(within(step).getByRole("textbox", { name: "Your explanation" })).toBeTruthy();
    // Only the start request so far: nothing is revealed or submitted by default.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("feedback quotes passages then offers three self-assessments", async () => {
    const grades: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [START]: () => jsonResponse(201, explainOnly),
        "POST /api/checkpoint-attempts/a2/response": () => jsonResponse(200, feedback),
        "POST /api/checkpoint-attempts/a2/grade": (init) => {
          grades.push(bodyOf(init));
          return jsonResponse(200, { quiz_item_id: "q1", due: "2026-10-02", state: 1 });
        },
      }),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    await screen.findByTestId("checkpoint-ask-explain");
    fireEvent.click(screen.getByRole("button", { name: "Sure" }));

    const step = await screen.findByTestId("checkpoint-feedback");
    expect(within(step).getByText(feedback.citations[0].quote)).toBeTruthy();
    expect(within(step).getByText("Book I › The Division of Labour")).toBeTruthy();
    const buttons = within(step)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(buttons).toEqual(["Missed it", "Partly", "Got it"]);

    fireEvent.click(within(step).getByRole("button", { name: "Partly" }));
    await screen.findByRole("button", { name: "Back to the book" });
    expect(grades).toEqual([{ rating: 2 }]);
  });

  it("feedback step shows no grade wording", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        [START]: () => jsonResponse(201, explainOnly),
        "POST /api/checkpoint-attempts/a2/response": () => jsonResponse(200, feedback),
      }),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    await screen.findByTestId("checkpoint-ask-explain");
    fireEvent.click(screen.getByRole("button", { name: "Not sure" }));

    const dialog = await screen.findByTestId("checkpoint-dialog");
    await within(dialog).findByTestId("checkpoint-feedback");
    expect(dialog.textContent).not.toMatch(
      /\b(score[sd]?|grade[sd]?|correct|incorrect|pass(ed)?|fail(ed)?)\b|%/i,
    );
  });

  it("closing mid-flow sends nothing more", async () => {
    const fetchMock = routedFetch({ [START]: () => jsonResponse(201, recallAndExplain) });
    vi.stubGlobal("fetch", fetchMock);
    const onClose = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Most" }));
    await screen.findByText("How many operations make a pin?");

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
