"""Dev-only read of the accumulated eval results (RFC-005 Cycle D).

One GET returning every discovered eval run with its aggregates and its derived
gate verdict. Read-only in the strongest sense: no write path exists, nothing is
re-run from here, and no provider is called — the handler reads files off disk.

Mounted only by a process that :func:`app.main.eval_dashboard_surface_exposed`
clears, and authenticated once mounted, so the surface is absent from production
and from any process that has not deliberately switched it on (AD-243).

The thresholds ride in the payload rather than living in the client, so the page
draws its reference lines from the same constants the nightly gate asserts and a
recalibration cannot leave a stale line on the chart.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.eval.ab import TierAggregate
from app.eval.judge import FAITHFULNESS_MIN, RELEVANCY_MIN, RESULTS_DIR
from app.eval.results import CaseRecord, RunMetrics, RunSummary, load_runs
from app.infrastructure.web.dependencies import AppSettings, get_authenticated_user

router = APIRouter(tags=["evals"])

#: How many runs one response carries, newest first, unless asked otherwise.
#: The nightly appends a run every night with no retention, and each run brings
#: its own cases, so an unbounded list grows without limit on a page that shows
#: the recent history. The discovered total travels alongside, so a bounded view
#: is visibly bounded rather than silently truncated.
DEFAULT_RUN_LIMIT = 25
MAX_RUN_LIMIT = 200

#: Carried in the payload so a reader cannot mistake a default checkout for the
#: whole eval history: locally the directory holds the committed golden files
#: only, while the nightly history accumulates on the ``eval-results`` branch.
SCOPE_NOTICE = (
    "Runs are read from the configured results directory on this process's disk. A default "
    "checkout holds only the committed result files; the accumulating nightly history lives on "
    "the eval-results branch, which LEARNY_EVAL_RESULTS_DIR can point at. Pass/fail is derived "
    "from the same thresholds the nightly gate asserts — it is not recorded in the data — so a "
    "run predating a recalibration is judged here by today's thresholds, not the ones it "
    "actually ran against. Runs judged by a different model are marked."
)


class ThresholdsView(BaseModel):
    """The gate constants in force, so the client never carries its own copy."""

    faithfulness_min: float
    relevancy_min: float


class RunMetricsView(BaseModel):
    """A run's headline numbers, over the same lines that produced its verdict."""

    scored: int
    answered: int
    mean_faithfulness: float | None
    mean_relevancy: float | None
    citation_valid_rate: float | None

    @classmethod
    def from_metrics(cls, metrics: RunMetrics) -> RunMetricsView:
        return cls(
            scored=metrics.scored,
            answered=metrics.answered,
            mean_faithfulness=metrics.mean_faithfulness,
            mean_relevancy=metrics.mean_relevancy,
            citation_valid_rate=metrics.citation_valid_rate,
        )


class TierMetricsView(BaseModel):
    """One tier's aggregates. ``None`` means *no lines to average*, never zero."""

    tier: str
    scored: int
    answered: int
    not_found_expected: int
    not_found_correct: int
    mean_faithfulness: float | None
    mean_relevancy: float | None
    citation_valid_rate: float | None
    not_found_discipline: float | None

    @classmethod
    def from_aggregate(cls, aggregate: TierAggregate) -> TierMetricsView:
        return cls(
            tier=aggregate.tier,
            scored=aggregate.scored,
            answered=aggregate.answered,
            not_found_expected=aggregate.not_found_expected,
            not_found_correct=aggregate.not_found_correct,
            mean_faithfulness=aggregate.mean_faithfulness,
            mean_relevancy=aggregate.mean_relevancy,
            citation_valid_rate=aggregate.citation_valid_rate,
            not_found_discipline=aggregate.not_found_discipline,
        )


class EvalCaseView(BaseModel):
    """One case, for the drill-down. Null scores mean declined, not zero."""

    case_id: str
    found: bool
    faithfulness: float | None
    relevancy: float | None
    citation_valid: bool
    tier: str | None
    status: str | None
    expected_not_found: bool
    run_index: int | None
    generation_model: str | None

    @classmethod
    def from_record(cls, record: CaseRecord) -> EvalCaseView:
        return cls(
            case_id=record.case_id,
            found=record.found,
            faithfulness=record.faithfulness,
            relevancy=record.relevancy,
            citation_valid=record.citation_valid,
            tier=record.tier,
            status=record.status,
            expected_not_found=record.expected_not_found,
            run_index=record.run_index,
            generation_model=record.generation_model,
        )


class EvalRunView(BaseModel):
    """One run: provenance, per-tier aggregates, derived verdict, and its cases."""

    run_id: str
    path: str
    latest_ts: str | None
    git_sha: str | None
    generation_model: str | None
    judge_model: str | None
    prompt_hash: str | None
    line_count: int
    unparsable: int
    verdict: str
    failures: list[str]
    metrics: RunMetricsView | None
    error_count: int
    other_count: int
    golden: TierMetricsView | None
    silver: TierMetricsView | None
    answerability_count: int
    answerability_mean_score: float | None
    cases: list[EvalCaseView]

    @classmethod
    def from_summary(cls, summary: RunSummary) -> EvalRunView:
        generation = summary.generation
        return cls(
            run_id=summary.run_id,
            path=summary.path,
            latest_ts=summary.latest_ts,
            git_sha=summary.git_sha,
            generation_model=summary.generation_model,
            judge_model=summary.judge_model,
            prompt_hash=summary.prompt_hash,
            line_count=summary.line_count,
            unparsable=summary.unparsable,
            verdict=summary.verdict,
            failures=list(summary.failures),
            metrics=RunMetricsView.from_metrics(summary.metrics) if summary.metrics else None,
            error_count=generation.error_count if generation else 0,
            other_count=generation.other_count if generation else 0,
            golden=TierMetricsView.from_aggregate(generation.golden) if generation else None,
            silver=TierMetricsView.from_aggregate(generation.silver) if generation else None,
            answerability_count=summary.answerability_count,
            answerability_mean_score=summary.answerability_mean_score,
            cases=[EvalCaseView.from_record(case) for case in summary.cases],
        )


class EvalDashboardView(BaseModel):
    """The whole surface: what it covers, where it read, and the runs it found."""

    scope: str
    results_dir: str
    #: The judge this process is configured with. A run judged by anything else
    #: was gated against thresholds derived for a different judge, so its
    #: recomputed verdict is not comparable — the page marks those rather than
    #: showing a wall of red that only means "the threshold moved".
    judge_model_in_force: str
    thresholds: ThresholdsView
    #: Runs discovered in the directory, which may exceed the number returned.
    total_runs: int
    runs: list[EvalRunView]


@router.get("/api/dev/evals", dependencies=[Depends(get_authenticated_user)])
def read_eval_runs(
    settings: AppSettings,
    limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIMIT)] = DEFAULT_RUN_LIMIT,
) -> EvalDashboardView:
    """Return the most recent eval runs, newest first.

    An empty list is the honest answer for a checkout where nothing has run, so
    a missing directory reads as no runs rather than as an error. ``total_runs``
    reports everything discovered, so a truncated view says so.
    """
    results_dir = settings.eval_results_dir or RESULTS_DIR
    runs = load_runs(results_dir)
    return EvalDashboardView(
        scope=SCOPE_NOTICE,
        results_dir=str(results_dir),
        judge_model_in_force=settings.judge_model,
        thresholds=ThresholdsView(faithfulness_min=FAITHFULNESS_MIN, relevancy_min=RELEVANCY_MIN),
        total_runs=len(runs),
        runs=[EvalRunView.from_summary(summary) for summary in runs[:limit]],
    )
