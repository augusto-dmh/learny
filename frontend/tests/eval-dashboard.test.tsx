// @vitest-environment jsdom

/**
 * The eval-results dashboard (EVDASH-06/08/09/10).
 *
 * Cases follow the spec's page criteria: the run list renders each run's verdict
 * and headline metrics, the drill-down opens and closes, a decline reads as a
 * decline rather than a zero, a citation violation is named, the trend carries
 * the threshold the *server* sent, and the ordinary "not enabled here" 404
 * settles to an explanation instead of an error.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { EvalDashboard } from "../app/components/eval-dashboard";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function tier(overrides: Record<string, unknown> = {}) {
  return {
    tier: "golden",
    scored: 2,
    answered: 2,
    not_found_expected: 0,
    not_found_correct: 0,
    mean_faithfulness: 1.0,
    mean_relevancy: 4.5,
    citation_valid_rate: 1.0,
    not_found_discipline: null,
    ...overrides,
  };
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "2026-07-30-aaa1111",
    path: "2026-07-30-aaa1111.jsonl",
    latest_ts: "2026-07-30T10:00:00+00:00",
    git_sha: "aaa1111",
    generation_model: "claude-sonnet-5",
    judge_model: "claude-opus-4-8",
    prompt_hash: "hash",
    line_count: 2,
    unparsable: 0,
    verdict: "pass",
    failures: [],
    error_count: 0,
    other_count: 0,
    golden: tier(),
    silver: tier({ tier: "silver", scored: 0, answered: 0, mean_faithfulness: null, mean_relevancy: null, citation_valid_rate: null }),
    answerability_count: 3,
    answerability_mean_score: 4.667,
    cases: [
      {
        case_id: "printing-movable-type",
        found: true,
        faithfulness: 1.0,
        relevancy: 5,
        citation_valid: true,
        tier: null,
        status: null,
        expected_not_found: false,
        run_index: null,
      },
    ],
    ...overrides,
  };
}

function dashboard(overrides: Record<string, unknown> = {}) {
  return {
    scope: "Runs are read from the configured results directory.",
    results_dir: "/repo/evals/results",
    judge_model_in_force: "claude-opus-4-8",
    thresholds: { faithfulness_min: 0.9, relevancy_min: 3.1 },
    runs: [run()],
    ...overrides,
  };
}

/** The value rendered against a metric label, so "1.000" is never ambiguous. */
function metricValue(label: string): string {
  const term = screen.getByText(label);
  return term.nextElementSibling?.textContent ?? "";
}

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => jsonResponse(status, body));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("EvalDashboard", () => {
  it("renders each run with its verdict and headline metrics", async () => {
    mockFetch(200, dashboard());

    render(<EvalDashboard />);

    expect(await screen.findByText("2026-07-30-aaa1111")).toBeTruthy();
    expect(screen.getByText("pass")).toBeTruthy();
    expect(metricValue("Faithfulness")).toBe("1.000");
    expect(metricValue("Relevancy")).toBe("4.500");
    expect(metricValue("Citations valid")).toBe("1.000");
    expect(screen.getByText("2026-07-30 10:00:00")).toBeTruthy();
  });

  it("says so when a run's records carry no timestamp", async () => {
    // Undated runs sort last rather than at an arbitrary position, so the row
    // has to admit the absence instead of rendering an invalid date.
    mockFetch(200, dashboard({ runs: [run({ latest_ts: null })] }));

    render(<EvalDashboard />);

    expect(await screen.findByText("undated")).toBeTruthy();
  });

  it("names which gate condition a failing run broke", async () => {
    mockFetch(
      200,
      dashboard({
        runs: [
          run({
            verdict: "fail",
            failures: ["faithfulness", "relevancy"],
            golden: tier({ mean_faithfulness: 0.2, mean_relevancy: 1 }),
          }),
        ],
      }),
    );

    render(<EvalDashboard />);

    expect(await screen.findByText("fail: faithfulness, relevancy")).toBeTruthy();
  });

  it("distinguishes a run that gated nothing from a passing run", async () => {
    mockFetch(
      200,
      dashboard({ runs: [run({ verdict: "not-evaluated", golden: null, silver: null, cases: [] })] }),
    );

    render(<EvalDashboard />);

    expect(await screen.findByText("not evaluated")).toBeTruthy();
  });

  it("reveals and hides the cases behind a run", async () => {
    mockFetch(200, dashboard());

    render(<EvalDashboard />);

    const toggle = await screen.findByRole("button", { name: "Show 1 cases" });
    expect(screen.queryByText("printing-movable-type")).toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByText("printing-movable-type")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Hide cases" }));
    await waitFor(() => expect(screen.queryByText("printing-movable-type")).toBeNull());
  });

  it("renders a decline as a decline rather than a zero score", async () => {
    mockFetch(
      200,
      dashboard({
        runs: [
          run({
            cases: [
              {
                case_id: "notfound-black-holes",
                found: false,
                faithfulness: null,
                relevancy: null,
                citation_valid: true,
                tier: null,
                status: null,
                expected_not_found: true,
                run_index: null,
              },
            ],
          }),
        ],
      }),
    );

    render(<EvalDashboard />);

    fireEvent.click(await screen.findByRole("button", { name: "Show 1 cases" }));

    expect(screen.getByText("declined (expected)")).toBeTruthy();
    // Absent scores read as absent — a decline scoring 0.000 would be a libel.
    expect(screen.queryByText("0.000")).toBeNull();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("marks the case that violated the citation invariant", async () => {
    mockFetch(
      200,
      dashboard({
        runs: [
          run({
            verdict: "fail",
            failures: ["citation"],
            cases: [
              {
                case_id: "broken-citation",
                found: true,
                faithfulness: 1.0,
                relevancy: 5,
                citation_valid: false,
                tier: null,
                status: null,
                expected_not_found: false,
                run_index: null,
              },
            ],
          }),
        ],
      }),
    );

    render(<EvalDashboard />);

    fireEvent.click(await screen.findByRole("button", { name: "Show 1 cases" }));

    expect(screen.getByText("invalid — citation invariant violated")).toBeTruthy();
  });

  it("draws the trend against the threshold the server sent", async () => {
    mockFetch(
      200,
      dashboard({
        thresholds: { faithfulness_min: 0.77, relevancy_min: 2.5 },
        runs: [
          run({ run_id: "newer", golden: tier({ mean_faithfulness: 0.95 }) }),
          run({ run_id: "older", golden: tier({ mean_faithfulness: 0.85 }) }),
        ],
      }),
    );

    render(<EvalDashboard />);

    // The reference line must track the server's constants, or a recalibration
    // would leave the page drawing a threshold nobody gates on.
    expect(
      await screen.findByRole("img", { name: /Mean faithfulness across 2 runs, threshold 0.77/ }),
    ).toBeTruthy();
  });

  it("omits a trend that has fewer than two points", async () => {
    mockFetch(200, dashboard());

    render(<EvalDashboard />);

    await screen.findByText("2026-07-30-aaa1111");
    expect(screen.queryByRole("img", { name: /Mean faithfulness/ })).toBeNull();
  });

  it("reports the answerability records that share the run's file", async () => {
    mockFetch(200, dashboard());

    render(<EvalDashboard />);

    expect(await screen.findByText("3 items, mean 4.67")).toBeTruthy();
  });

  it("marks a run judged by a model other than the one in force", async () => {
    // Nine of the eleven real historical runs are haiku-judged and recompute as
    // failures purely because Cycle B moved the relevancy threshold. Unmarked,
    // the page's loudest signal would be a wall of red that means nothing.
    mockFetch(
      200,
      dashboard({
        runs: [run({ judge_model: "claude-haiku-4-5", verdict: "fail", failures: ["relevancy"] })],
      }),
    );

    render(<EvalDashboard />);

    expect(
      await screen.findByText(/judged by claude-haiku-4-5 — verdict recomputed/),
    ).toBeTruthy();
  });

  it("does not mark a run judged by the model in force", async () => {
    mockFetch(200, dashboard());

    render(<EvalDashboard />);

    await screen.findByText("2026-07-30-aaa1111");
    expect(screen.queryByText(/verdict recomputed/)).toBeNull();
  });

  it("explains a disabled surface instead of reporting an error", async () => {
    mockFetch(404, { detail: "Not Found" });

    render(<EvalDashboard />);

    expect(await screen.findByText(/not enabled on this process/)).toBeTruthy();
  });

  it("offers a retry when the read fails", async () => {
    mockFetch(500, { detail: "boom" });

    render(<EvalDashboard />);

    expect(await screen.findByText(/could not be read \(500\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("reports an empty results directory as empty", async () => {
    mockFetch(200, dashboard({ runs: [] }));

    render(<EvalDashboard />);

    expect(await screen.findByText(/No eval runs found in/)).toBeTruthy();
  });
});
