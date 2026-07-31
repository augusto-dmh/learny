"""Committed generation A/B study runner (RFC-005 Cycle C).

The 2026-07-21 generation A/B ran through an ad-hoc, uncommitted driver and a
prior attempt died mid-judge on credit exhaustion. This module is the committed
replacement: a checkpointed, resumable, budget-capped runner over study *units*
— one ``(tier, case, arm, run_index)`` generation+judging — that appends one
JSONL line per unit immediately after scoring, so an interruption costs only
the unfinished unit.

Provider- and DB-agnostic by injection, like :mod:`tests.eval.silver`: the live
entrypoint (``test_generation_study.py``) wires real adapters; unit tests wire
fakes. Golden lines are tracked (synthetic book, no copyrighted text); silver
lines stay under the git-ignored ``evals/silver/results/`` (AD-163). Budget is
enforced against **modeled** unit costs (AD-234): the runner refuses to start a
unit that would cross ``settings.eval_budget_usd``, stopping at a clean
checkpoint the next invocation resumes from.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.entities import Evidence
from app.eval.ab import ModelAggregate, aggregate
from tests.eval.harness import EvalCase, Snapshot, build_snapshot, snapshot_eval_inputs

GOLDEN = "golden"
SILVER = "silver"

# The two study arms (AD-166 heritage) and the run count (AD-235).
ARMS = ("claude-sonnet-5", "claude-opus-4-8")
RUNS = 3

# One unit's identity inside the artifacts: the resume key.
UnitKey = tuple[str, str, str, int]


class StudyMismatchError(RuntimeError):
    """A study artifact was produced under a different judge or prompt hash.

    Mixing such lines into one study would aggregate incomparable scores — the
    runner refuses before any spend (DENOISE-06).
    """


@dataclass(frozen=True)
class StudyUnit:
    """One generation+judging: a case, on one arm, in one seeded run."""

    tier: str
    case_id: str
    arm: str
    run_index: int

    @property
    def key(self) -> UnitKey:
        return (self.tier, self.case_id, self.arm, self.run_index)


@dataclass(frozen=True)
class CostModel:
    """Modeled per-unit provider cost (AD-234) — modeled, never billed-metered.

    ``generation_usd_per_unit`` maps each arm's model to the modeled cost of one
    generation call; ``judge_usd_per_unit`` is the modeled cost of one unit's
    judge calls (both metrics together). The live entrypoint pins the amounts
    from observed token counts and current prices.
    """

    generation_usd_per_unit: Mapping[str, float]
    judge_usd_per_unit: float

    def unit_cost(self, arm: str) -> float:
        """The modeled cost of scoring one unit on ``arm``."""
        return self.generation_usd_per_unit[arm] + self.judge_usd_per_unit


@dataclass
class StudyReport:
    """What one runner invocation did (counters, not lines — lines live on disk)."""

    scored: int = 0
    skipped: int = 0
    budget_stopped: bool = False
    modeled_spent_usd: float = 0.0
    paths: list[Path] = field(default_factory=list)


def plan_units(
    golden_case_ids: Sequence[str],
    silver_case_ids: Sequence[str],
    *,
    arms: Sequence[str] = ARMS,
    runs: int = RUNS,
) -> list[StudyUnit]:
    """The full study in its canonical order: tier → run → case → arm.

    A budget stop truncates this order, so whole early runs complete before
    later ones start — a partial study still contains comparable full runs.
    """
    units: list[StudyUnit] = []
    for tier, case_ids in ((GOLDEN, golden_case_ids), (SILVER, silver_case_ids)):
        for run_index in range(runs):
            for case_id in case_ids:
                for arm in arms:
                    units.append(
                        StudyUnit(tier=tier, case_id=case_id, arm=arm, run_index=run_index)
                    )
    return units


def load_recorded(
    golden_path: Path,
    silver_path: Path,
    *,
    prompt_hash_value: str,
    judge_model: str,
) -> dict[UnitKey, str]:
    """Read both study artifacts back into a resume map (unit key → status).

    Any line carrying a judge identity must match the current configuration —
    a drifted ``prompt_hash`` or ``judge_model`` raises :class:`StudyMismatchError`
    before any spend. Lines without judge identity (declines, skipped, broken)
    are legitimate and pass through (ADR-028). Absent artifacts mean a fresh
    study.
    """
    recorded: dict[UnitKey, str] = {}
    for path in (golden_path, silver_path):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = json.loads(raw)
            recorded_hash = line.get("prompt_hash")
            if recorded_hash is not None and recorded_hash != prompt_hash_value:
                raise StudyMismatchError(
                    f"{path.name} was recorded under prompt_hash {recorded_hash!r}, "
                    f"current is {prompt_hash_value!r} — start a fresh artifact"
                )
            recorded_judge = line.get("judge_model")
            if recorded_judge is not None and recorded_judge != judge_model:
                raise StudyMismatchError(
                    f"{path.name} was recorded under judge {recorded_judge!r}, "
                    f"current is {judge_model!r} — start a fresh artifact"
                )
            key = (line["tier"], line["case_id"], line["generation_model"], line["run_index"])
            recorded[key] = line["status"]
    return recorded


# Statuses that consumed provider calls — the only ones that bill modeled cost.
_BILLED_STATUSES = frozenset({"ok", "error"})
# Statuses that count a unit as complete on resume; error re-attempts.
_COMPLETE_STATUSES = frozenset({"ok", "skipped", "broken"})


def _append_line(path: Path, line: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def run_study(
    units: Sequence[StudyUnit],
    *,
    score: Callable[[StudyUnit], dict[str, Any]],
    recorded: Mapping[UnitKey, str],
    cost_model: CostModel,
    budget_usd: float,
    golden_path: Path,
    silver_path: Path,
    git_sha: str,
    progress: Callable[[str], None] = print,
    now: Callable[[], datetime] | None = None,
) -> StudyReport:
    """Score every not-yet-recorded unit, checkpointing one JSONL line each.

    Per unit: skip when ``recorded`` marks it complete (ok/skipped/broken —
    zero provider calls; error re-attempts); stop *before* any unit whose
    modeled cost would cross ``budget_usd`` (recorded ok/error lines count
    toward the ceiling exactly once — they billed when first scored); otherwise
    call ``score`` and append the line immediately — a scorer exception becomes
    a visible ``error`` line and the study continues (DEEP-17 heritage). The
    unit's identity fields on the line always come from the unit, never the
    scorer.
    """
    clock = now or (lambda: datetime.now(UTC))
    spent = sum(
        cost_model.unit_cost(key[2])
        for key, status in recorded.items()
        if status in _BILLED_STATUSES
    )
    report = StudyReport(modeled_spent_usd=spent)
    report.paths = [golden_path, silver_path]

    for unit in units:
        if recorded.get(unit.key) in _COMPLETE_STATUSES:
            report.skipped += 1
            progress(f"{unit.tier}/{unit.case_id}/{unit.arm}/run{unit.run_index}: recorded, skip")
            continue

        unit_cost = cost_model.unit_cost(unit.arm)
        if report.modeled_spent_usd + unit_cost > budget_usd:
            report.budget_stopped = True
            progress(
                f"budget stop before {unit.tier}/{unit.case_id}/{unit.arm}/run{unit.run_index}: "
                f"modeled ${report.modeled_spent_usd:.2f} + ${unit_cost:.2f} would cross "
                f"${budget_usd:.2f} — resume with a raised LEARNY_EVAL_BUDGET_USD"
            )
            break

        try:
            fields = score(unit)
        except Exception as exc:  # noqa: BLE001 — a failed unit is a visible error line
            fields = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "faithfulness": None,
                "relevancy": None,
            }
        if fields.get("status") == "ok":
            fields.setdefault("expected_not_found", False)

        line = {
            "ts": clock().isoformat(),
            **fields,
            "case_id": unit.case_id,
            "tier": unit.tier,
            "generation_model": unit.arm,
            "run_index": unit.run_index,
            "git_sha": git_sha,
        }
        _append_line(golden_path if unit.tier == GOLDEN else silver_path, line)
        report.scored += 1
        report.modeled_spent_usd += unit_cost
        progress(f"{unit.tier}/{unit.case_id}/{unit.arm}/run{unit.run_index}: {line['status']}")
    return report


def domain_evidence(snapshot: Snapshot) -> list[Evidence]:
    """Rebuild adapter-ready :class:`Evidence` from a committed snapshot.

    The snapshot records only ``(chunk_id, snippet, anchor)``; the fields the
    generation prompt never reads are placeholdered (``section_path=()`` makes
    the document title fall back to the anchor — identical across both arms, so
    the A/B stays fair; recorded as a study limitation).
    """
    return [
        Evidence(
            chunk_id=UUID(item.chunk_id),
            source_id=UUID(int=0),
            section_path=(),
            anchor=item.anchor,
            page_span=None,
            snippet=item.snippet,
            score=0.0,
        )
        for item in snapshot.evidence
    ]


def score_golden_unit(
    case: EvalCase,
    evidence: Sequence[Any],
    *,
    generate: Callable[[str, Sequence[Any]], Any],
    judge: Any,
    judge_prompt_hash: str,
) -> dict[str, Any]:
    """Generate over frozen evidence and judge the answer — one golden unit.

    Citation validity and the decline outcome come from the committed replay
    logic (:func:`build_snapshot` + :func:`snapshot_eval_inputs`), so the study
    and the nightly tier share one definition. A declined answer is never
    judge-called and carries null scores with no judge identity (ADR-028).
    """
    generated = generate(case.question, evidence)
    fresh = build_snapshot(case, evidence, generated)
    [eval_input] = snapshot_eval_inputs([fresh])
    scores: dict[str, Any]
    if eval_input.found:
        faithfulness = judge.faithfulness(
            question=eval_input.question,
            evidence=eval_input.evidence_text,
            answer=eval_input.answer_text,
        ).supported_ratio
        relevancy = judge.relevancy(question=eval_input.question, answer=eval_input.answer_text)
        scores = {
            "faithfulness": float(faithfulness),
            "relevancy": int(relevancy),
            "judge_model": str(judge.model),
            "prompt_hash": judge_prompt_hash,
        }
    else:
        scores = {"faithfulness": None, "relevancy": None}
    return {
        "status": "ok",
        "generation_model": str(eval_input.generation_model),
        **scores,
        "found": eval_input.found,
        "citation_valid": eval_input.citation_valid,
        "expected_not_found": case.expected_status == "not_found_in_source",
    }


def per_run_aggregates(
    lines: Sequence[dict[str, Any]], *, arm: str, runs: int = RUNS
) -> list[ModelAggregate]:
    """One :func:`app.eval.ab.aggregate` per seeded run for one arm.

    The returned list feeds :func:`app.eval.ab.metric_spread` and
    :func:`app.eval.ab.denoised_generation_verdict`.
    """
    return [
        aggregate(
            [
                line
                for line in lines
                if line.get("generation_model") == arm and line.get("run_index") == run_index
            ]
        )
        for run_index in range(runs)
    ]
