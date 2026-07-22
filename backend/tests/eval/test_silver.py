"""The committed live silver runner (markers ``live`` + ``eval``, DEEP-01/03/19/20).

Runs the local silver tier end-to-end: resolve each case by checksum + anchor
against the real corpus DB, retrieve over it, generate with the settings-default
Anthropic model, judge with the anchored Haiku rubric, and append one JSONL line
per case to the git-ignored ``evals/silver/results/`` (a fresh file per run).

The module **self-skips at import** when the local data, provider keys, or corpus
DB url are absent — so CI and fresh clones stay green with *zero* provider SDK
imports on that path (the SDK/DB imports live inside the test body, after the
guard). The deterministic proof of that skip lives in ``test_silver_run.py``; the
real run happens in Phase D on the maintainer's machine.
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from tests.eval.silver import (
    BrokenCase,
    ResolvedCase,
    SilverJudgement,
    SkippedCase,
    broken_result,
    load_silver_cases,
    resolve_case,
    run_silver_case,
    silver_run_skip_reason,
    skipped_result,
    write_silver_results,
)

_SKIP_REASON = silver_run_skip_reason()
if _SKIP_REASON:  # module-level: no provider import happens past this point on skip
    pytest.skip(_SKIP_REASON, allow_module_level=True)

pytestmark = [pytest.mark.live, pytest.mark.eval]


def test_silver_tier_runs_over_the_local_corpus() -> None:
    # Provider/DB imports are deliberately inside the body — the skip path above
    # never reaches them (DEEP-03).
    from sqlalchemy import create_engine

    from app.core.config import get_settings
    from app.eval.judge import Judge, prompt_hash
    from app.infrastructure.answering.anthropic import AnthropicAnswerAdapter
    from tests.eval_runner import retrieve as retrieve_evidence

    settings = get_settings()
    api_key = os.environ["LEARNY_ANTHROPIC_API_KEY"]
    cases = load_silver_cases()
    adapter = AnthropicAnswerAdapter(
        api_key=api_key,
        model=settings.generation_model,
        max_tokens=settings.generation_max_tokens,
    )
    judge = Judge(api_key=api_key, model=settings.judge_model)
    judge_prompt_hash = prompt_hash()

    def judge_call(question, evidence, answer) -> SilverJudgement:  # noqa: ANN001
        evidence_text = "\n\n".join(item.snippet for item in evidence)
        faithfulness = judge.faithfulness(
            question=question, evidence=evidence_text, answer=answer.text
        )
        relevancy = judge.relevancy(question=question, answer=answer.text)
        return SilverJudgement(
            faithfulness=faithfulness.supported_ratio,
            relevancy=relevancy,
            model=judge.model,
            prompt_hash=judge_prompt_hash,
        )

    engine = create_engine(settings.database_url, future=True)
    lines: list[dict] = []
    try:
        with engine.connect() as conn:
            for case in cases:
                resolution = resolve_case(conn, case)
                if isinstance(resolution, SkippedCase):
                    lines.append(skipped_result(resolution))
                elif isinstance(resolution, BrokenCase):
                    lines.append(broken_result(resolution))
                else:
                    assert isinstance(resolution, ResolvedCase)
                    lines.append(
                        run_silver_case(
                            resolution,
                            retrieve=lambda r: retrieve_evidence(
                                conn,
                                UUID(r.source_id),
                                r.case.question,
                                top_k=settings.qa_evidence_top_k,
                            ),
                            generate=lambda q, ev: adapter.generate(question=q, evidence=ev),
                            judge=judge_call,
                        )
                    )
    finally:
        engine.dispose()

    path = write_silver_results(lines)
    assert path.exists()
    # The local corpus is ingested, so at least one case must actually run (not
    # every case skipped/broken) — otherwise the silver set has drifted off the DB.
    assert any(line["status"] in {"ok", "error"} for line in lines)
