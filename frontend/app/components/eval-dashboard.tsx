"use client";

/**
 * The eval-results dashboard (EVDASH-06/07/08/09/10).
 *
 * A read-only render of the nightly eval JSONL that has accumulated since v2
 * with nothing displaying it. Everything shown comes from one GET; the component
 * computes no metric of its own, and in particular draws its threshold reference
 * lines from the values the server sends, so a recalibration moves the lines
 * without a frontend change.
 *
 * The endpoint is mounted only by a process that has deliberately enabled it and
 * is not production, so a 404 is the ordinary answer rather than a fault — it
 * settles to an explanatory state, not an error.
 *
 * The trend is hand-drawn SVG on purpose: no charting dependency enters the tree
 * for one dev-only page, and the series colours come from the design tokens the
 * rest of the app already defines.
 */

import { useCallback, useEffect, useState } from "react";

const ENDPOINT = "/api/dev/evals";

type TierMetrics = {
  tier: string;
  scored: number;
  answered: number;
  not_found_expected: number;
  not_found_correct: number;
  mean_faithfulness: number | null;
  mean_relevancy: number | null;
  citation_valid_rate: number | null;
  not_found_discipline: number | null;
};

type EvalCase = {
  case_id: string;
  found: boolean;
  faithfulness: number | null;
  relevancy: number | null;
  citation_valid: boolean;
  tier: string | null;
  status: string | null;
  expected_not_found: boolean;
  run_index: number | null;
};

type EvalRun = {
  run_id: string;
  path: string;
  latest_ts: string | null;
  git_sha: string | null;
  generation_model: string | null;
  judge_model: string | null;
  prompt_hash: string | null;
  line_count: number;
  unparsable: number;
  verdict: string;
  failures: string[];
  error_count: number;
  other_count: number;
  golden: TierMetrics | null;
  silver: TierMetrics | null;
  answerability_count: number;
  answerability_mean_score: number | null;
  cases: EvalCase[];
};

type Dashboard = {
  scope: string;
  results_dir: string;
  judge_model_in_force: string;
  thresholds: { faithfulness_min: number; relevancy_min: number };
  runs: EvalRun[];
};

type State =
  | { kind: "loading" }
  | { kind: "disabled" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Dashboard };

function formatNumber(value: number | null, digits = 3): string {
  return value === null ? "—" : value.toFixed(digits);
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "undated";
  const parsed = new Date(ts);
  return Number.isNaN(parsed.getTime()) ? ts : parsed.toISOString().replace("T", " ").slice(0, 19);
}

/** The tier a run's headline numbers come from: silver when it has any, else golden. */
function headlineTier(run: EvalRun): TierMetrics | null {
  if (run.silver && run.silver.scored > 0) return run.silver;
  return run.golden;
}

function VerdictBadge({ verdict, failures }: { verdict: string; failures: string[] }) {
  const tone =
    verdict === "pass"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
      : verdict === "fail"
        ? "bg-red-500/15 text-red-700 dark:text-red-300"
        : "bg-muted text-muted-foreground";
  const label = verdict === "not-evaluated" ? "not evaluated" : verdict;
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {label}
      {failures.length > 0 ? `: ${failures.join(", ")}` : ""}
    </span>
  );
}

/**
 * One metric's per-run series with its gate threshold drawn across it.
 *
 * The point of the drawing is the reference line: a mean drifting toward the
 * threshold is the thing a table of numbers hides. Points run oldest to newest,
 * left to right.
 */
function MetricTrend({
  label,
  points,
  threshold,
  domain,
}: {
  label: string;
  points: { runId: string; value: number }[];
  threshold: number;
  domain: [number, number];
}) {
  if (points.length < 2) return null;

  const width = 320;
  const height = 96;
  const padding = 8;
  const [low, high] = domain;
  const span = high - low || 1;
  const x = (index: number) =>
    padding + (index * (width - 2 * padding)) / Math.max(points.length - 1, 1);
  const y = (value: number) =>
    height - padding - ((value - low) / span) * (height - 2 * padding);

  const polyline = points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ");
  const thresholdY = y(threshold);
  const latest = points[points.length - 1];

  return (
    <figure className="space-y-1">
      <figcaption className="text-xs text-muted-foreground">
        {label} — latest {latest.value.toFixed(3)}, threshold {threshold}
      </figcaption>
      <svg
        role="img"
        aria-label={`${label} across ${points.length} runs, threshold ${threshold}`}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-sm"
        preserveAspectRatio="none"
      >
        <line
          x1={padding}
          x2={width - padding}
          y1={thresholdY}
          y2={thresholdY}
          stroke="var(--color-chart-5)"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--color-chart-1)"
          strokeWidth={2}
        />
        {points.map((point, index) => (
          <circle
            key={point.runId}
            cx={x(index)}
            cy={y(point.value)}
            r={2.5}
            fill={point.value < threshold ? "var(--color-chart-5)" : "var(--color-chart-1)"}
          />
        ))}
      </svg>
    </figure>
  );
}

function CaseTable({ cases }: { cases: EvalCase[] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-muted-foreground">
        <tr>
          <th className="py-1 pr-3 font-medium">Case</th>
          <th className="py-1 pr-3 font-medium">Outcome</th>
          <th className="py-1 pr-3 font-medium">Faithfulness</th>
          <th className="py-1 pr-3 font-medium">Relevancy</th>
          <th className="py-1 font-medium">Citations</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((item) => (
          <tr key={`${item.case_id}-${item.run_index ?? 0}`} className="border-t border-border">
            <td className="py-1 pr-3 font-mono">{item.case_id}</td>
            <td className="py-1 pr-3">
              {/* A decline is its own outcome, never a zero-scoring answer (ADR-0028). */}
              {item.found ? "answered" : "declined"}
              {item.expected_not_found ? " (expected)" : ""}
            </td>
            <td className="py-1 pr-3">{formatNumber(item.faithfulness)}</td>
            <td className="py-1 pr-3">{formatNumber(item.relevancy, 0)}</td>
            <td className="py-1">
              {item.citation_valid ? "valid" : "invalid — citation invariant violated"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RunRow({ run, judgeInForce }: { run: EvalRun; judgeInForce: string }) {
  const [expanded, setExpanded] = useState(false);
  const tier = headlineTier(run);
  // A run judged by another model was gated against thresholds derived for that
  // model. Its verdict here is recomputed with today's, so the comparison is not
  // like-for-like and the row has to say so next to the badge.
  const staleJudge = run.judge_model !== null && run.judge_model !== judgeInForce;
  return (
    <li className="border-t border-border py-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="font-mono text-sm">{run.run_id}</span>
        <VerdictBadge verdict={run.verdict} failures={run.failures} />
        <span className="text-xs text-muted-foreground">{formatTimestamp(run.latest_ts)}</span>
        {staleJudge ? (
          <span className="text-xs text-amber-700 dark:text-amber-400">
            judged by {run.judge_model} — verdict recomputed with the current thresholds
          </span>
        ) : null}
      </div>
      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <div>
          <dt className="inline text-muted-foreground">Faithfulness </dt>
          <dd className="inline font-medium">{formatNumber(tier?.mean_faithfulness ?? null)}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Relevancy </dt>
          <dd className="inline font-medium">{formatNumber(tier?.mean_relevancy ?? null)}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Citations valid </dt>
          <dd className="inline font-medium">{formatNumber(tier?.citation_valid_rate ?? null)}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Answerability </dt>
          <dd className="inline font-medium">
            {run.answerability_count === 0
              ? "none"
              : `${run.answerability_count} items, mean ${formatNumber(run.answerability_mean_score, 2)}`}
          </dd>
        </div>
        {run.generation_model ? (
          <div>
            <dt className="inline text-muted-foreground">Generation </dt>
            <dd className="inline font-medium">{run.generation_model}</dd>
          </div>
        ) : null}
        {run.judge_model ? (
          <div>
            <dt className="inline text-muted-foreground">Judge </dt>
            <dd className="inline font-medium">{run.judge_model}</dd>
          </div>
        ) : null}
        {run.unparsable > 0 ? (
          <div>
            <dt className="inline text-muted-foreground">Unparsable lines </dt>
            <dd className="inline font-medium">{run.unparsable}</dd>
          </div>
        ) : null}
      </dl>
      {run.cases.length > 0 ? (
        <>
          <button
            type="button"
            className="mt-2 text-xs underline underline-offset-2"
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? "Hide cases" : `Show ${run.cases.length} cases`}
          </button>
          {expanded ? (
            <div className="mt-2">
              <CaseTable cases={run.cases} />
            </div>
          ) : null}
        </>
      ) : null}
    </li>
  );
}

export function EvalDashboard() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const resp = await fetch(ENDPOINT, { credentials: "same-origin" });
      if (resp.status === 404) {
        setState({ kind: "disabled" });
        return;
      }
      if (!resp.ok) {
        setState({ kind: "error", message: `The eval results could not be read (${resp.status}).` });
        return;
      }
      setState({ kind: "ready", data: (await resp.json()) as Dashboard });
    } catch {
      setState({ kind: "error", message: "The eval results could not be read." });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return <p className="text-muted-foreground">Loading eval runs…</p>;
  }

  if (state.kind === "disabled") {
    return (
      <p className="text-muted-foreground">
        The eval dashboard is not enabled on this process. Set the dashboard flag on a
        non-production process to read the accumulated results.
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="space-y-2">
        <p className="text-muted-foreground">{state.message}</p>
        <button type="button" className="text-xs underline underline-offset-2" onClick={() => void load()}>
          Try again
        </button>
      </div>
    );
  }

  const { data } = state;

  if (data.runs.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-muted-foreground">No eval runs found in {data.results_dir}.</p>
        <p className="text-xs text-muted-foreground">{data.scope}</p>
      </div>
    );
  }

  // Trends read left to right in time, so the newest-first list is reversed here
  // rather than the server changing its order for one consumer.
  const chronological = [...data.runs].reverse();
  const series = (pick: (run: EvalRun) => number | null) =>
    chronological
      .map((run) => ({ runId: run.run_id, value: pick(run) }))
      .filter((point): point is { runId: string; value: number } => point.value !== null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <MetricTrend
          label="Mean faithfulness"
          points={series((run) => headlineTier(run)?.mean_faithfulness ?? null)}
          threshold={data.thresholds.faithfulness_min}
          domain={[0, 1]}
        />
        <MetricTrend
          label="Mean relevancy"
          points={series((run) => headlineTier(run)?.mean_relevancy ?? null)}
          threshold={data.thresholds.relevancy_min}
          domain={[1, 5]}
        />
      </div>
      <ul className="border-b border-border">
        {data.runs.map((run) => (
          <RunRow key={run.run_id} run={run} judgeInForce={data.judge_model_in_force} />
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Read from {data.results_dir}. {data.scope}
      </p>
    </div>
  );
}
