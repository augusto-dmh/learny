"""Unit tests for the A/B study logic (`app.eval.ab`).

Pure logic — no DB, no provider, no keys. Lines here mirror the two producers'
shapes: golden `run_eval` lines (no `tier`/`status`) and silver `run_silver_case`
lines (tier=silver, status ok/error, plus skipped/broken). Tests derive from
DEEP-10..15 and the recorded not-found / threshold decisions.
"""

from __future__ import annotations

from app.eval.ab import (
    Agreement,
    ModelAggregate,
    TierAggregate,
    aggregate,
    generation_verdict,
    judge_agreement,
    judge_verdict,
)


def _golden(
    case_id: str,
    *,
    faithfulness: float,
    relevancy: int,
    citation_valid: bool = True,
    **extra,
):
    """A golden `run_eval`-shaped line (no tier, no status)."""
    return {
        "case_id": case_id,
        "generation_model": "claude-sonnet-5",
        "faithfulness": faithfulness,
        "relevancy": relevancy,
        "citation_valid": citation_valid,
        **extra,
    }


def _silver(
    case_id: str,
    *,
    faithfulness: float,
    relevancy: int,
    citation_valid: bool = True,
    status: str = "ok",
    **extra,
):
    """A silver `run_silver_case`-shaped line (tier=silver, explicit status)."""
    return {
        "case_id": case_id,
        "generation_model": "claude-sonnet-5",
        "tier": "silver",
        "status": status,
        "faithfulness": faithfulness,
        "relevancy": relevancy,
        "citation_valid": citation_valid,
        **extra,
    }


# --- empty / degenerate (invariant: never reads as passing) --------------------


def test_empty_input_yields_none_means_not_zero():
    agg = aggregate([])
    assert agg.line_count == 0
    assert agg.error_count == 0
    for tier in (agg.golden, agg.silver):
        assert tier.scored == 0
        # None, not 0.0 — an empty aggregate must not look like a real (failing) score.
        assert tier.mean_faithfulness is None
        assert tier.mean_relevancy is None
        assert tier.citation_valid_rate is None
        assert tier.not_found_discipline is None


def test_all_error_input_has_no_means_and_a_visible_error_count():
    agg = aggregate([_silver("s1", faithfulness=0.0, relevancy=1, status="error")])
    assert agg.error_count == 1
    assert agg.silver.scored == 0
    assert agg.silver.mean_faithfulness is None


# --- tier split (DEEP-13/14: metrics split golden vs silver) -------------------


def test_missing_tier_lines_land_in_golden():
    agg = aggregate([_golden("g1", faithfulness=1.0, relevancy=4)])
    assert agg.golden.scored == 1
    assert agg.silver.scored == 0


def test_mixed_tiers_split_and_average_independently():
    agg = aggregate(
        [
            _golden("g1", faithfulness=1.0, relevancy=4),
            _golden("g2", faithfulness=0.8, relevancy=2),
            _silver("s1", faithfulness=0.5, relevancy=5),
        ]
    )
    assert agg.golden.scored == 2
    assert agg.golden.mean_faithfulness == 0.9
    assert agg.golden.mean_relevancy == 3.0
    assert agg.silver.scored == 1
    assert agg.silver.mean_faithfulness == 0.5
    assert agg.silver.mean_relevancy == 5.0


def test_citation_valid_rate_is_the_fraction_valid():
    agg = aggregate(
        [
            _golden("g1", faithfulness=1.0, relevancy=4, citation_valid=True),
            _golden("g2", faithfulness=1.0, relevancy=4, citation_valid=False),
        ]
    )
    assert agg.golden.citation_valid_rate == 0.5


# --- error / non-ok line handling (invariant: excluded from means, visible) ----


def test_error_lines_excluded_from_means_but_counted():
    agg = aggregate(
        [
            _silver("s1", faithfulness=1.0, relevancy=4),
            _silver("s2", faithfulness=0.0, relevancy=1, status="error"),
        ]
    )
    assert agg.error_count == 1
    assert agg.silver.scored == 1  # the error line is not scored
    assert agg.silver.mean_faithfulness == 1.0  # error's 0.0 did not drag the mean


def test_skipped_and_broken_lines_counted_as_other_not_scored():
    agg = aggregate(
        [
            _silver("s1", faithfulness=1.0, relevancy=4),
            _silver("s2", faithfulness=0.0, relevancy=1, status="skipped"),
            _silver("s3", faithfulness=0.0, relevancy=1, status="broken"),
        ]
    )
    assert agg.other_count == 2
    assert agg.error_count == 0
    assert agg.silver.scored == 1
    # Full accounting: every input line is scored, error, or other.
    accounted = (
        agg.golden.scored + agg.silver.scored + agg.error_count + agg.other_count
    )
    assert agg.line_count == accounted


# --- not-found handling (recorded decision) ------------------------------------


def test_relevancy_mean_excludes_declined_lines():
    # A decline (found False) scores relevancy 1 by construction; it must not drag
    # the relevancy mean, but it still counts toward faithfulness (vacuously 1.0).
    agg = aggregate(
        [
            _silver("s1", faithfulness=1.0, relevancy=4, found=True),
            _silver("s2", faithfulness=1.0, relevancy=1, found=False),
        ]
    )
    assert agg.silver.answered == 1
    assert agg.silver.mean_relevancy == 4.0  # only the answered line
    assert agg.silver.mean_faithfulness == 1.0  # both lines


def test_not_found_discipline_is_correct_declines_over_expected_not_found():
    agg = aggregate(
        [
            # expected not-found, correctly declined
            _golden("g1", faithfulness=1.0, relevancy=1, found=False, expected_not_found=True),
            # expected not-found, wrongly answered
            _golden("g2", faithfulness=1.0, relevancy=3, found=True, expected_not_found=True),
            # answerable case (not part of discipline)
            _golden("g3", faithfulness=1.0, relevancy=4, found=True, expected_not_found=False),
        ]
    )
    assert agg.golden.not_found_expected == 2
    assert agg.golden.not_found_correct == 1
    assert agg.golden.not_found_discipline == 0.5


def test_not_found_discipline_is_none_without_expected_not_found_cases():
    # Silver cases are all authored answerable → no expected_not_found → discipline None.
    agg = aggregate([_silver("s1", faithfulness=1.0, relevancy=4, found=True)])
    assert agg.silver.not_found_discipline is None


# --- judge_agreement (DEEP-10/11: pairing, agreement rates, gate flips) --------


def _jline(case_id: str, *, model: str = "claude-sonnet-5", faithfulness: float, relevancy: int):
    """A judged line as either judge would emit for one (case, generation model)."""
    return {
        "case_id": case_id,
        "generation_model": model,
        "faithfulness": faithfulness,
        "relevancy": relevancy,
    }


def test_agreement_pairs_by_case_and_generation_model_excluding_unpaired():
    a = [
        _jline("c1", faithfulness=1.0, relevancy=4),
        _jline("c2", faithfulness=1.0, relevancy=3),
    ]
    b = [
        _jline("c1", faithfulness=1.0, relevancy=4),
        _jline("c2", faithfulness=1.0, relevancy=3),
        _jline("c3", faithfulness=1.0, relevancy=5),  # unpaired — only judge b saw it
    ]
    result = judge_agreement(a, b)
    assert result.n == 2  # c3 excluded


def test_same_case_different_generation_model_does_not_pair():
    a = [_jline("c1", model="claude-sonnet-5", faithfulness=1.0, relevancy=4)]
    b = [_jline("c1", model="claude-opus-4-8", faithfulness=1.0, relevancy=4)]
    result = judge_agreement(a, b)
    assert result.n == 0
    assert result.exact is None
    assert result.within_1 is None


def test_exact_and_within_1_rates():
    a = [
        _jline("c1", faithfulness=1.0, relevancy=4),
        _jline("c2", faithfulness=1.0, relevancy=4),
        _jline("c3", faithfulness=1.0, relevancy=4),
        _jline("c4", faithfulness=1.0, relevancy=4),
    ]
    b = [
        _jline("c1", faithfulness=1.0, relevancy=4),  # exact
        _jline("c2", faithfulness=1.0, relevancy=5),  # within 1
        _jline("c3", faithfulness=1.0, relevancy=3),  # within 1
        _jline("c4", faithfulness=1.0, relevancy=1),  # off by 3
    ]
    result = judge_agreement(a, b)
    assert result.n == 4
    assert result.exact == 0.25  # only c1
    assert result.within_1 == 0.75  # c1, c2, c3


def test_gate_flip_counts_disagreement_on_passing_the_gate():
    # RELEVANCY_MIN 2.8 → relevancy 3 passes, 2 fails; FAITHFULNESS_MIN 0.90.
    a = [_jline("c1", faithfulness=1.0, relevancy=3)]  # passes
    b = [_jline("c1", faithfulness=1.0, relevancy=2)]  # fails → flip
    result = judge_agreement(a, b)
    assert result.gate_flips == 1


def test_no_gate_flip_when_both_judges_pass():
    a = [_jline("c1", faithfulness=1.0, relevancy=5)]
    b = [_jline("c1", faithfulness=0.95, relevancy=3)]  # both clear the gate
    result = judge_agreement(a, b)
    assert result.gate_flips == 0


# --- judge_verdict boundaries (AD-165: switch < 0.60 / < 0.90 / any flip) ------


def test_judge_verdict_keeps_at_exact_threshold():
    assert judge_verdict(Agreement(n=5, exact=0.60, within_1=1.0, gate_flips=0)) == "keep"


def test_judge_verdict_switches_below_exact_threshold():
    assert judge_verdict(Agreement(n=5, exact=0.59, within_1=1.0, gate_flips=0)) == "switch"


def test_judge_verdict_keeps_at_within_1_threshold():
    assert judge_verdict(Agreement(n=10, exact=1.0, within_1=0.90, gate_flips=0)) == "keep"


def test_judge_verdict_switches_below_within_1_threshold():
    assert judge_verdict(Agreement(n=10, exact=1.0, within_1=0.89, gate_flips=0)) == "switch"


def test_judge_verdict_switches_on_any_gate_flip():
    assert judge_verdict(Agreement(n=5, exact=1.0, within_1=1.0, gate_flips=1)) == "switch"


def test_judge_verdict_keeps_on_full_agreement():
    assert judge_verdict(Agreement(n=5, exact=1.0, within_1=1.0, gate_flips=0)) == "keep"


def test_judge_verdict_keeps_without_paired_evidence():
    assert judge_verdict(Agreement(n=0, exact=None, within_1=None, gate_flips=0)) == "keep"


# --- generation_verdict boundaries (AD-166: ≥2 better on silver, none worse) ---


def _arm(
    *,
    faithfulness: float | None,
    relevancy: float | None,
    discipline: float | None,
) -> ModelAggregate:
    """A ModelAggregate whose silver tier carries the three driving metrics."""
    silver = TierAggregate(
        tier="silver",
        scored=1,
        answered=1,
        not_found_expected=0,
        not_found_correct=0,
        mean_faithfulness=faithfulness,
        mean_relevancy=relevancy,
        citation_valid_rate=1.0,
        not_found_discipline=discipline,
    )
    golden = TierAggregate(
        tier="golden",
        scored=0,
        answered=0,
        not_found_expected=0,
        not_found_correct=0,
        mean_faithfulness=None,
        mean_relevancy=None,
        citation_valid_rate=None,
        not_found_discipline=None,
    )
    return ModelAggregate(
        line_count=1, error_count=0, other_count=0, golden=golden, silver=silver
    )


def test_generation_moves_when_opus_better_on_two_and_worse_on_none():
    sonnet = _arm(faithfulness=0.9, relevancy=3.0, discipline=None)
    opus = _arm(faithfulness=0.95, relevancy=3.5, discipline=None)
    assert generation_verdict(sonnet, opus) == "move"


def test_generation_stays_when_opus_better_on_only_one():
    sonnet = _arm(faithfulness=0.9, relevancy=3.0, discipline=None)
    opus = _arm(faithfulness=0.95, relevancy=3.0, discipline=None)  # relevancy tie
    assert generation_verdict(sonnet, opus) == "stay"


def test_generation_stays_when_opus_worse_on_any_metric():
    sonnet = _arm(faithfulness=0.9, relevancy=3.0, discipline=0.8)
    opus = _arm(faithfulness=0.95, relevancy=3.5, discipline=0.7)  # worse discipline
    assert generation_verdict(sonnet, opus) == "stay"


def test_generation_treats_a_tie_as_not_better():
    sonnet = _arm(faithfulness=0.9, relevancy=3.0, discipline=0.8)
    opus = _arm(faithfulness=0.9, relevancy=3.0, discipline=0.8)
    assert generation_verdict(sonnet, opus) == "stay"


def test_generation_moves_on_all_three_metrics():
    sonnet = _arm(faithfulness=0.9, relevancy=3.0, discipline=0.7)
    opus = _arm(faithfulness=0.95, relevancy=3.5, discipline=0.9)
    assert generation_verdict(sonnet, opus) == "move"


def test_generation_stays_when_silver_has_no_comparable_metrics():
    # Degenerate: no silver data on either arm → nothing better → conservative stay.
    sonnet = _arm(faithfulness=None, relevancy=None, discipline=None)
    opus = _arm(faithfulness=None, relevancy=None, discipline=None)
    assert generation_verdict(sonnet, opus) == "stay"
