"""A/B study logic: pure aggregation + verdict helpers for the eval-deepening cycle.

Two studies feed one research doc: a **judge A/B** (Haiku 4.5 vs Opus 4.8 scoring
identical outputs) and a **generation A/B** (Sonnet 5 vs Opus 4.8 over golden +
silver). This module is the only place their recorded decision thresholds live, and
it is pure: no provider SDK, no network, no DB. Phase D feeds it the recorded result
lines and reads back per-model aggregates, judge-agreement rates, and the
keep/switch and stay/move verdicts.

Input line contract
--------------------
A *result line* is a plain dict as written by the study runners
(:func:`app.eval.judge.run_eval` for golden, ``tests.eval.silver.run_silver_case``
for silver). Fields this module reads, with the default applied when a field is
absent (so raw ``run_eval`` lines, which omit ``tier``/``status``/``found``, still
aggregate):

- ``case_id: str``             — required; pairs judge-A/B lines.
- ``generation_model: str``    — required; pairs judge-A/B lines (both producers emit it).
- ``faithfulness: float``      — supported-claim ratio (0..1).
- ``relevancy: int``           — 1..5.
- ``citation_valid: bool``     — deterministic citation invariant.
- ``tier: str``                — ``"golden"`` | ``"silver"``; **absent → "golden"**.
- ``status: str``              — ``"ok"`` scored, ``"error"`` excluded-but-counted, any
                                 other non-``ok`` status excluded (skipped/broken);
                                 **absent → "ok"**.
- ``found: bool``              — did the model answer (vs decline)? **absent → True**.
- ``expected_not_found: bool`` — is the case unanswerable by design? **absent → False**.

Not-found handling (recorded decisions, tasks.md Phase B status line): a decline
scores relevancy 1 *by construction* (an empty answer is off-topic), so the
**relevancy mean excludes declined lines** (``found`` False); faithfulness treats a
decline as vacuously faithful (ratio 1.0) and keeps it in the mean, matching the
existing gate. **Not-found discipline** is its own metric — the
decline-when-unanswerable rate over the ``expected_not_found`` cases — and is
``None`` for a tier with no such cases. Silver cases are all authored answerable, so
silver discipline is ``None`` and does not drive the generation verdict; faithfulness
and relevancy do.

Phase D must emit ``found`` and ``expected_not_found`` on every line to get not-found
handling right; the defaults keep raw lines aggregatable (all treated as
answered/answerable) but then yield no not-found signal.

Degenerate inputs never read as passing: every mean/rate is ``None`` (not ``0.0``)
when it has no lines to average, so an empty or all-error aggregate is visibly empty
rather than a silent zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

GOLDEN = "golden"
SILVER = "silver"


@dataclass(frozen=True)
class TierAggregate:
    """One tier's metrics for one generation model (``None`` mean/rate = no lines).

    ``scored`` counts metric-bearing lines (status ok); ``answered`` the subset the
    model actually answered (``found``). ``mean_relevancy`` averages only the
    answered lines (declines score 1 by construction); ``mean_faithfulness`` and
    ``citation_valid_rate`` cover all scored lines. ``not_found_discipline`` is
    ``not_found_correct / not_found_expected`` — the decline-when-unanswerable rate —
    or ``None`` when the tier has no ``expected_not_found`` case.
    """

    tier: str
    scored: int
    answered: int
    not_found_expected: int
    not_found_correct: int
    mean_faithfulness: float | None
    mean_relevancy: float | None
    citation_valid_rate: float | None
    not_found_discipline: float | None


@dataclass(frozen=True)
class ModelAggregate:
    """A generation model's full study aggregate, split golden vs silver.

    ``line_count`` is every input line; it equals ``golden.scored + silver.scored +
    error_count + other_count`` (error = ``status`` error, other = skipped/broken and
    any non-``ok`` status). Errors are excluded from every mean but stay visible here
    so an all-error run cannot masquerade as a passing one.
    """

    line_count: int
    error_count: int
    other_count: int
    golden: TierAggregate
    silver: TierAggregate


def _tier_of(line: dict[str, Any]) -> str:
    """A line's tier: ``"silver"`` only when tagged so, else ``"golden"`` (the default)."""
    return SILVER if line.get("tier") == SILVER else GOLDEN


def _mean(values: Iterable[float]) -> float | None:
    """Arithmetic mean, or ``None`` for an empty sequence (never a misleading 0.0)."""
    materialized = list(values)
    if not materialized:
        return None
    return sum(materialized) / len(materialized)


def _tier_aggregate(tier: str, lines: list[dict[str, Any]]) -> TierAggregate:
    """Build one tier's :class:`TierAggregate` from its scored lines."""
    answered = [line for line in lines if line.get("found", True)]
    not_found_expected = [line for line in lines if line.get("expected_not_found", False)]
    not_found_correct = [
        line for line in not_found_expected if not line.get("found", True)
    ]
    discipline = (
        len(not_found_correct) / len(not_found_expected) if not_found_expected else None
    )
    return TierAggregate(
        tier=tier,
        scored=len(lines),
        answered=len(answered),
        not_found_expected=len(not_found_expected),
        not_found_correct=len(not_found_correct),
        mean_faithfulness=_mean(float(line["faithfulness"]) for line in lines),
        mean_relevancy=_mean(float(line["relevancy"]) for line in answered),
        citation_valid_rate=_mean(
            1.0 if line["citation_valid"] else 0.0 for line in lines
        ),
        not_found_discipline=discipline,
    )


def aggregate(lines: Sequence[dict[str, Any]]) -> ModelAggregate:
    """Aggregate result lines into per-tier metrics (see the module contract).

    Scored (status ``ok``) lines feed the tier metrics; ``error`` lines are counted
    and excluded from every mean; other non-``ok`` statuses (skipped/broken) are
    counted and excluded. An empty input yields all-``None`` means, not zeros.
    """
    scored: dict[str, list[dict[str, Any]]] = {GOLDEN: [], SILVER: []}
    error_count = 0
    other_count = 0
    for line in lines:
        status = line.get("status", "ok")
        if status == "ok":
            scored[_tier_of(line)].append(line)
        elif status == "error":
            error_count += 1
        else:
            other_count += 1
    return ModelAggregate(
        line_count=len(lines),
        error_count=error_count,
        other_count=other_count,
        golden=_tier_aggregate(GOLDEN, scored[GOLDEN]),
        silver=_tier_aggregate(SILVER, scored[SILVER]),
    )
