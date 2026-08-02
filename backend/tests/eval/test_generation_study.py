"""The committed live entrypoint for the generation A/B study (RFC-005 Cycle C).

Runs both arms × the seeded runs over the golden replay cases (frozen snapshot
evidence, DB-free) and the local silver tier (resolved once per study), judged
by the pinned :data:`STUDY_JUDGE_MODEL`, through :func:`tests.eval.study.run_study`
— checkpointed, resumable, and budget-capped against ``settings.eval_budget_usd``.

Deliberately **not** enrolled in the nightly ``-m "live and eval"`` selection
(the ``eval`` marker is absent — guarded offline in ``test_study_runner``): a
two-arm study is an operator decision with real spend, opted into explicitly:

    uv run pytest tests/eval/test_generation_study.py --generation-study -q

Silver requires the local corpus DB and the git-ignored cases file; when either
is absent the study runs golden-only and says so (the silver-driving verdict
then stays "stay" by incomparability — recorded, never silently passing).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import pytest

from tests.eval.study import ARMS, GOLDEN

# The judge the study's pre-registered rule and the nightly thresholds are
# calibrated to (the recalibration flip). Pinned here — NOT read from settings
# — because a stale env pin once judged a full study with the wrong model; the
# offline pin test ties this constant to the config default so a future judge
# flip must update both deliberately.
STUDY_JUDGE_MODEL = "claude-opus-4-8"

# Modeled per-unit costs (USD) for the budget meter (AD-234), 2026-07-31 prices
# (sonnet-5 $3/$15, opus-4-8 $5/$25 per MTok). A generation unit budgets ~3k
# evidence/prompt tokens in and ~2k out (answer + adaptive thinking, billed as
# output); a judge unit budgets the two structured calls at ~4k in / ~0.5k out
# — the recalibration's observed judge spend (≈$0.009/unit over 36 units) says
# this is conservative. Deliberately rounded up; the research doc's spend
# report reconciles modeled vs actual.
_JUDGE_USD_PER_UNIT = 0.015
_GENERATION_USD_PER_UNIT = {
    "claude-sonnet-5": 0.035,
    "claude-opus-4-8": 0.055,
}


def study_skip_reason(config: pytest.Config) -> str | None:
    """Why the study must not run in this invocation (``None`` = clear to spend)."""
    if not config.getoption("--generation-study"):
        return "pass --generation-study to run the paid two-arm generation study"
    if not os.getenv("LEARNY_ANTHROPIC_API_KEY"):
        return "LEARNY_ANTHROPIC_API_KEY required for the live study"
    return None


@pytest.fixture
def _study_enabled(request: pytest.FixtureRequest) -> None:
    reason = study_skip_reason(request.config)
    if reason:
        pytest.skip(reason)


@pytest.mark.live
def test_generation_study_runs_both_arms_over_seeded_runs(_study_enabled: None) -> None:
    # Provider/DB imports live inside the body so collection stays offline-safe.
    from app.core.config import get_settings
    from app.domain.entities import MODE_ANSWER
    from app.eval.judge import RESULTS_DIR, Judge, git_sha_of_head, prompt_hash
    from app.infrastructure.answering.anthropic import AnthropicGenerationAdapter
    from tests.eval.harness import load_cases, load_snapshots
    from tests.eval.silver import (
        SILVER_RESULTS_DIR,
        BrokenCase,
        ResolvedCase,
        SkippedCase,
        broken_result,
        judge_adapter,
        load_silver_cases,
        resolve_case,
        run_silver_case,
        silver_run_skip_reason,
        skipped_result,
    )
    from tests.eval.study import (
        CostModel,
        StudyUnit,
        domain_evidence,
        load_recorded,
        memoize_retrieval,
        plan_units,
        run_study,
        score_golden_unit,
    )

    settings = get_settings()
    api_key = os.environ["LEARNY_ANTHROPIC_API_KEY"]
    judge = Judge(api_key=api_key, model=STUDY_JUDGE_MODEL)
    judge_prompt_hash = prompt_hash()
    git_sha = git_sha_of_head()

    adapters = {
        arm: AnthropicGenerationAdapter(
            api_key=api_key, model=arm, max_tokens=settings.generation_max_tokens
        )
        for arm in ARMS
    }

    judge_call = judge_adapter(judge, judge_prompt_hash)

    # Golden: the committed replay cases with their frozen snapshot evidence.
    snapshots = {snapshot.case_id: snapshot for snapshot in load_snapshots()}
    golden_cases = {case.case_id: case for case in load_cases() if case.case_id in snapshots}
    golden_evidence = {
        case_id: domain_evidence(snapshot) for case_id, snapshot in snapshots.items()
    }

    # Silver: resolved once per study; retrieval memoized per case so evidence
    # stays fixed across arms and runs.
    silver_skip = silver_run_skip_reason()
    resolutions: dict[str, ResolvedCase | SkippedCase | BrokenCase] = {}
    memoized_retrieve = None
    engine = None
    conn = None
    if silver_skip is None:
        from sqlalchemy import create_engine

        from tests.eval_runner import retrieve as retrieve_evidence

        engine = create_engine(settings.database_url, future=True)
        conn = engine.connect()
        for case in load_silver_cases():
            resolutions[case.case_id] = resolve_case(conn, case)

        memoized_retrieve = memoize_retrieval(
            lambda resolved: retrieve_evidence(
                conn,
                UUID(resolved.source_id),
                resolved.case.question,
                top_k=settings.conversation_evidence_top_k,
            )
        )
    else:
        print(f"silver tier unavailable ({silver_skip}) — running golden-only")

    def score(unit: StudyUnit) -> dict:
        arm_generate = lambda question, evidence: adapters[unit.arm].generate(  # noqa: E731
            message=question, mode=MODE_ANSWER, evidence=evidence
        )
        if unit.tier == GOLDEN:
            return score_golden_unit(
                golden_cases[unit.case_id],
                golden_evidence[unit.case_id],
                generate=arm_generate,
                judge=judge,
                judge_prompt_hash=judge_prompt_hash,
            )
        resolution = resolutions[unit.case_id]
        if isinstance(resolution, SkippedCase):
            return skipped_result(resolution)
        if isinstance(resolution, BrokenCase):
            return broken_result(resolution)
        return run_silver_case(
            resolution, retrieve=memoized_retrieve, generate=arm_generate, judge=judge_call
        )

    date = datetime.now(UTC).strftime("%Y-%m-%d")
    golden_path = RESULTS_DIR / f"{date}-{git_sha}-generation-denoise.jsonl"
    silver_path = SILVER_RESULTS_DIR / f"{date}-{git_sha}-generation-denoise.jsonl"

    try:
        recorded = load_recorded(
            golden_path,
            silver_path,
            prompt_hash_value=judge_prompt_hash,
            judge_model=STUDY_JUDGE_MODEL,
        )
        units = plan_units(sorted(golden_cases), sorted(resolutions))
        report = run_study(
            units,
            score=score,
            recorded=recorded,
            cost_model=CostModel(
                generation_usd_per_unit=_GENERATION_USD_PER_UNIT,
                judge_usd_per_unit=_JUDGE_USD_PER_UNIT,
            ),
            budget_usd=settings.eval_budget_usd,
            golden_path=golden_path,
            silver_path=silver_path,
            git_sha=git_sha,
        )
    finally:
        if conn is not None:
            conn.close()
        if engine is not None:
            engine.dispose()

    print(
        f"study invocation: scored {report.scored}, skipped {report.skipped}, "
        f"modeled ${report.modeled_spent_usd:.2f}, budget_stopped={report.budget_stopped}"
    )
    assert golden_path.exists()
    # A budget stop is a clean checkpoint, not a failure — resume finishes it.
    if not report.budget_stopped:
        assert report.scored + report.skipped == len(units)
