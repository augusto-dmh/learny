"""RoutingGenerationAdapter — buffered fallback policy + attribution (unit, fakes).

Derived from the routing acceptance criteria: the router implements
``GenerationPort`` over an ordered profile chain and serves from the first entry
that can (ROUTE-01); ``Timeout``/``ProviderUnavailable`` fail over to the next
entry, ``RateLimited`` earns exactly one same-entry retry before crossing, and
``RequestRejected`` crosses only to an entry whose adapter builds a different
request shape (ROUTE-02, AD-337); an exhausted chain re-raises the last
translated error so the application's ``AnswerGenerationFailed`` envelope is
unchanged (TAX-03); and every result names the profile that served it
(ROUTE-08, AD-344) so spend maps to the serving catalog.

No network and no provider SDK: the chain entries wrap scripted fakes whose
outcomes drive each policy branch.
"""

from __future__ import annotations

import pytest

from app.domain.entities import GeneratedAnswer
from app.infrastructure.answering.routing import ChainEntry, RoutingGenerationAdapter
from app.infrastructure.providers import (
    GenerationProfileSettings,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

_MODE = "answer"


# --- Scripted chain doubles --------------------------------------------------------


class _ScriptedAdapter:
    """``GenerationPort`` double: each buffered call pops its next scripted outcome.

    An outcome that is an ``Exception`` subclass is raised; anything else is
    returned. ``calls`` is the zero-calls sensor the policy assertions lean on.
    """

    def __init__(self, model: str, outcomes: list[object]) -> None:
        self.model = model
        self._outcomes = list(outcomes)
        self.calls = 0

    def generate(self, **_kwargs: object) -> GeneratedAnswer:  # noqa: ANN003 — port kwargs
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, GeneratedAnswer)
        return outcome

    def generate_stream(self, **_kwargs: object) -> object:  # noqa: ANN003, ANN202
        raise AssertionError("streaming policy is a separate acceptance criterion")


def _answer(text: str) -> GeneratedAnswer:
    return GeneratedAnswer(text=text, cited_chunk_ids=(), model="unused", found=True)


def _profile(
    id: str,  # noqa: A002 — the settings field is named ``id``
    kind: str = "anthropic",
) -> GenerationProfileSettings:
    return GenerationProfileSettings(
        id=id,
        kind=kind,  # type: ignore[arg-type]
        model=f"{id}-model",
        max_tokens=1024,
        price_input_usd_per_million_tokens=3.0,
        price_output_usd_per_million_tokens=15.0,
        price_cache_read_usd_per_million_tokens=0.3,
        price_cache_creation_usd_per_million_tokens=3.75,
        grounding="verified-spans",
        ask_enabled=True,
        teach_enabled=True,
    )


def _chain(*specs: tuple[str, str, _ScriptedAdapter]) -> tuple[ChainEntry, ...]:
    return tuple(
        ChainEntry(adapter=adapter, profile=_profile(pid, kind)) for pid, kind, adapter in specs
    )


def _router(*specs: tuple[str, str, _ScriptedAdapter]) -> RoutingGenerationAdapter:
    return RoutingGenerationAdapter(_chain(*specs))


# --- First eligible entry serves, and the result carries its stamp -----------------


def test_the_first_entry_serves_and_stamps_the_result_with_its_profile() -> None:
    second = _ScriptedAdapter("b-model", [])
    router = _router(
        ("primary", "anthropic", _ScriptedAdapter("a-model", [_answer("from primary")])),
        ("fallback", "local", second),
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from primary"
    assert answer.profile_id == "primary"
    assert second.calls == 0  # no fail-over on success


def test_the_router_reports_the_primary_model_without_any_call() -> None:
    primary = _ScriptedAdapter("a-model", [])
    router = _router(("primary", "anthropic", primary))

    assert router.model == "a-model"
    assert primary.calls == 0  # readable without touching the chain (QA-04)


# --- Each error class drives its policy branch (ROUTE-02 / AD-337) ------------------


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(Timeout("slow"), id="timeout"),
        pytest.param(ProviderUnavailable("5xx"), id="provider-unavailable"),
    ],
)
def test_a_transport_failure_fails_over_to_the_next_entry(error: Exception) -> None:
    second = _ScriptedAdapter("b-model", [_answer("from fallback")])
    router = _router(
        ("primary", "anthropic", _ScriptedAdapter("a-model", [error])),
        ("fallback", "local", second),
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from fallback"
    assert answer.profile_id == "fallback"
    assert second.calls == 1


def test_a_rate_limit_earns_exactly_one_same_entry_retry() -> None:
    primary = _ScriptedAdapter("a-model", [RateLimited("429"), _answer("retry ok")])
    second = _ScriptedAdapter("b-model", [])
    router = _router(("primary", "anthropic", primary), ("fallback", "local", second))

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "retry ok"
    assert answer.profile_id == "primary"
    assert primary.calls == 2  # the throttled call plus its one retry — no more
    assert second.calls == 0  # the retry stayed on the same entry


def test_a_retry_that_fails_again_fails_over_to_the_next_entry() -> None:
    primary = _ScriptedAdapter("a-model", [RateLimited("429"), RateLimited("429 again")])
    second = _ScriptedAdapter("b-model", [_answer("from fallback")])
    router = _router(("primary", "anthropic", primary), ("fallback", "local", second))

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from fallback"
    assert primary.calls == 2  # exactly the one retry was spent on the entry
    assert second.calls == 1  # then the chain crossed


def test_each_entry_earns_its_own_single_rate_limit_retry() -> None:
    # The retry belongs to the throttled entry, not to the turn: the primary's
    # spent retry does not consume the fallback's, and a Timeout on the retry
    # still crosses (any non-success advances).
    primary = _ScriptedAdapter("a-model", [RateLimited("429"), Timeout("retry hung")])
    second = _ScriptedAdapter(
        "b-model", [RateLimited("429"), _answer("fallback after its own retry")]
    )
    router = _router(("primary", "anthropic", primary), ("fallback", "local", second))

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "fallback after its own retry"
    assert answer.profile_id == "fallback"
    assert primary.calls == 2
    assert second.calls == 2  # the fallback earned (and used) its own one retry


def test_a_request_rejection_crosses_only_to_a_different_request_shape() -> None:
    # A rejection is a verdict on the request shape: the same-kind sibling would
    # rebuild it verbatim and earn the same rejection, so it is skipped without
    # a call; the different-kind adapter may build a different request.
    rejected = _ScriptedAdapter("a1-model", [RequestRejected("400")])
    same_kind = _ScriptedAdapter("a2-model", [])
    different = _ScriptedAdapter("b-model", [_answer("from the other shape")])
    router = _router(
        ("primary", "anthropic", rejected),
        ("sibling", "anthropic", same_kind),
        ("fallback", "local", different),
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from the other shape"
    assert answer.profile_id == "fallback"
    assert same_kind.calls == 0
    assert different.calls == 1


def test_a_request_rejection_with_no_different_kind_raises() -> None:
    rejected = _ScriptedAdapter("a1-model", [RequestRejected("400")])
    same_kind = _ScriptedAdapter("a2-model", [])
    router = _router(
        ("primary", "anthropic", rejected),
        ("sibling", "anthropic", same_kind),
    )

    with pytest.raises(RequestRejected):
        router.generate(mode=_MODE, message="q", evidence=[])

    assert same_kind.calls == 0


# --- Exhausted chain and unrecognized failures (envelope unchanged) ----------------


def test_an_exhausted_chain_reraises_the_last_translated_error() -> None:
    last = ProviderUnavailable("the last one")
    router = _router(
        ("primary", "anthropic", _ScriptedAdapter("a-model", [Timeout("first")])),
        ("mid", "local", _ScriptedAdapter("b-model", [Timeout("second")])),
        ("tail", "anthropic", _ScriptedAdapter("c-model", [last])),
    )

    with pytest.raises(ProviderUnavailable) as excinfo:
        router.generate(mode=_MODE, message="q", evidence=[])

    assert excinfo.value is last  # the exact error the tail raised


def test_an_unrecognized_failure_propagates_unchanged_without_failover() -> None:
    error = RuntimeError("not a transport signal")
    second = _ScriptedAdapter("b-model", [])
    router = _router(
        ("primary", "anthropic", _ScriptedAdapter("a-model", [error])),
        ("fallback", "local", second),
    )

    with pytest.raises(RuntimeError) as excinfo:
        router.generate(mode=_MODE, message="q", evidence=[])

    assert excinfo.value is error
    assert second.calls == 0


# --- Attribution from every chain position (ROUTE-08 / AD-344) ----------------------


@pytest.mark.parametrize("position", [0, 1, 2], ids=["primary", "middle", "tail"])
def test_the_stamp_names_whichever_entry_served(position: int) -> None:
    ids = ["primary", "middle", "tail"]
    specs: list[tuple[str, str, _ScriptedAdapter]] = []
    for index, pid in enumerate(ids):
        outcomes: list[object] = (
            [_answer(f"from {pid}")] if index == position else [Timeout("not this one")]
        )
        kind = "anthropic" if index % 2 == 0 else "local"
        specs.append((pid, kind, _ScriptedAdapter(f"{pid}-model", outcomes)))
    router = _router(*specs)

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.profile_id == ids[position]
    assert answer.text == f"from {ids[position]}"
