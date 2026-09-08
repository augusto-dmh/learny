"""RoutingGenerationAdapter — fallback policy, streaming rule, attribution (fakes).

Derived from the routing acceptance criteria: the router implements
``GenerationPort`` over an ordered profile chain and serves from the first entry
that can (ROUTE-01); ``Timeout``/``ProviderUnavailable`` fail over to the next
entry, ``RateLimited`` earns exactly one same-entry retry before crossing, and
``RequestRejected`` crosses only to an entry whose adapter builds a different
request shape (ROUTE-02, AD-337); an exhausted chain re-raises the last
translated error so the application's ``AnswerGenerationFailed`` envelope is
unchanged (TAX-03); every result names the profile that served it (ROUTE-08,
AD-344) so spend maps to the serving catalog; a stream fails over only before
its first delta and the completed answer carries the stamp (ROUTE-04); and a
grounded mode routes only over entries enabled for it, failing honest with zero
provider touches when none is (ROUTE-03).

No network and no provider SDK: the chain entries wrap scripted fakes whose
outcomes drive each policy branch.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.domain.entities import (
    MODE_TEACH,
    SENTINEL,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    GeneratedAnswer,
)
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
    *,
    ask: bool = True,
    teach: bool = True,
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
        ask_enabled=ask,
        teach_enabled=teach,
    )


def _chain(*specs: tuple[str, str, _ScriptedAdapter]) -> tuple[ChainEntry, ...]:
    return tuple(
        ChainEntry(adapter=adapter, profile=_profile(pid, kind)) for pid, kind, adapter in specs
    )


def _router(
    *specs: tuple[str, str, _ScriptedAdapter], rate_retry_delay: float = 0.0
) -> RoutingGenerationAdapter:
    """A router over the scripted chain.

    Tests default the rate-limit backoff to 0 so the suite stays offline and
    fast; the backoff's *amounts* are the subject of the dedicated tests below,
    which patch the sleep and pass their own values.
    """
    return RoutingGenerationAdapter(_chain(*specs), rate_retry_delay=rate_retry_delay)


def _entry(
    id: str,  # noqa: A002 — the settings field is named ``id``
    adapter: _ScriptedAdapter,
    *,
    kind: str = "anthropic",
    ask: bool = True,
    teach: bool = True,
) -> ChainEntry:
    return ChainEntry(adapter=adapter, profile=_profile(id, kind, ask=ask, teach=teach))


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


# --- The same-entry retry waits a bounded backoff first (ROUTE-02) ------------------


def test_the_same_entry_retry_is_requested_only_after_one_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr("app.infrastructure.answering.routing.time.sleep", waits.append)
    primary = _ScriptedAdapter("a-model", [RateLimited("429"), _answer("retry ok")])
    second = _ScriptedAdapter("b-model", [])
    router = _router(
        ("primary", "anthropic", primary),
        ("fallback", "local", second),
        rate_retry_delay=0.0,
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    # The wait was requested exactly once, before the one same-entry retry —
    # not around the fail-over, and not twice for one throttle.
    assert waits == [0.0]
    assert answer.text == "retry ok"
    assert answer.profile_id == "primary"
    assert primary.calls == 2
    assert second.calls == 0


def test_the_backoff_defaults_to_the_router_delay_without_a_provider_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr("app.infrastructure.answering.routing.time.sleep", waits.append)
    primary = _ScriptedAdapter("a-model", [RateLimited("429"), _answer("retry ok")])
    router = _router(("primary", "anthropic", primary), rate_retry_delay=1.0)

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    # No hint from the adapter, so the router's default backoff is what was
    # requested (patched, so the suite never actually sleeps).
    assert waits == [1.0]
    assert answer.text == "retry ok"


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        pytest.param(2.0, 2.0, id="short-hint-honored"),
        pytest.param(99.0, 5.0, id="long-hint-capped"),
    ],
)
def test_the_backoff_honors_the_provider_hint_capped_to_bound_the_turn(
    hint: float,
    expected: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr("app.infrastructure.answering.routing.time.sleep", waits.append)
    primary = _ScriptedAdapter(
        "a-model", [RateLimited("429", retry_after=hint), _answer("retry ok")]
    )
    router = _router(("primary", "anthropic", primary), rate_retry_delay=0.0)

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    # The provider's hint wins over the default, but the cap — not the hint —
    # sets the worst case a reader's turn can be made to wait.
    assert waits == [expected]
    assert answer.text == "retry ok"


def test_a_pre_delta_rate_limit_retry_sleeps_before_reentering_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr("app.infrastructure.answering.routing.time.sleep", waits.append)
    first = _StreamScriptedAdapter(
        "a-model", [[RateLimited("429")], [AnswerCompleted(answer=_answer("retry ok"))]]
    )
    router = _stream_router(_entry("primary", first), rate_retry_delay=0.0)

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    # The pre-delta window obeys the buffered policy exactly — backoff included.
    assert waits == [0.0]
    assert first.stream_calls == 2
    assert isinstance(events[-1], AnswerCompleted)


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


# --- Streaming doubles --------------------------------------------------------------


class _StreamScriptedAdapter:
    """``GenerationPort`` double for the streaming rule.

    Each ``generate_stream`` call pops the next script: a list whose items are
    either events (yielded in order) or exceptions (raised at that point). A
    script whose first item is an exception fails **before any delta** — the
    fail-over window; an exception after a yielded event is a post-delta
    failure. ``closed`` records whether the consumer closed the last stream it
    opened, so the cancellation contract is observable.
    """

    def __init__(self, model: str, scripts: list[list[object]]) -> None:
        self.model = model
        self._scripts = [list(script) for script in scripts]
        self.stream_calls = 0
        self.closed = False

    def generate(self, **_kwargs: object) -> GeneratedAnswer:  # noqa: ANN003
        raise AssertionError("buffered policy is covered by the scripted double above")

    def generate_stream(self, **_kwargs: object) -> Iterator[AnswerStreamEvent]:  # noqa: ANN003
        self.stream_calls += 1
        script = self._scripts.pop(0)
        adapter = self

        def _gen() -> Iterator[AnswerStreamEvent]:
            try:
                for item in script:
                    if isinstance(item, Exception):
                        raise item
                    assert isinstance(item, (AnswerTextDelta, AnswerCompleted))
                    yield item
            except GeneratorExit:
                adapter.closed = True
                raise

        return _gen()


def _stream_router(*entries: ChainEntry, rate_retry_delay: float = 0.0) -> RoutingGenerationAdapter:
    """A streaming router over the scripted entries (see ``_router`` for the 0 backoff)."""
    return RoutingGenerationAdapter(tuple(entries), rate_retry_delay=rate_retry_delay)


def _collect(events: Iterator[AnswerStreamEvent]) -> list[AnswerStreamEvent]:
    return list(events)


# --- ROUTE-04: fail over only before the first delta --------------------------------


def test_a_pre_delta_stream_failure_fails_over_to_the_next_entry() -> None:
    first = _StreamScriptedAdapter("a-model", [[Timeout("hung before speaking")]])
    second = _StreamScriptedAdapter(
        "b-model", [[AnswerTextDelta(text="hello"), AnswerCompleted(answer=_answer("hello"))]]
    )
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert [type(event) for event in events] == [AnswerTextDelta, AnswerCompleted]
    assert second.stream_calls == 1
    # The completed answer is authoritative and names the profile that served it.
    assert isinstance(events[-1], AnswerCompleted)
    assert events[-1].answer.profile_id == "fallback"


def test_a_post_delta_failure_propagates_once_with_no_second_completed() -> None:
    first = _StreamScriptedAdapter(
        "a-model",
        [[AnswerTextDelta(text="partial"), ProviderUnavailable("mid-answer outage")]],
    )
    second = _StreamScriptedAdapter("b-model", [[AnswerCompleted(answer=_answer("x"))]])
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    seen: list[AnswerStreamEvent] = []
    with pytest.raises(ProviderUnavailable) as excinfo:
        for event in router.generate_stream(mode=_MODE, message="q", evidence=[]):
            seen.append(event)

    # The delta went out, then the error — exactly once, with no fail-over and
    # no second AnswerCompleted after it.
    assert [type(event) for event in seen] == [AnswerTextDelta]
    assert excinfo.value.args == ("mid-answer outage",)
    assert second.stream_calls == 0


def test_the_stream_policy_walk_matches_the_buffered_one_pre_delta() -> None:
    # The same policy governs the pre-delta window: the rate-limited entry earns
    # exactly one same-entry retry before the chain crosses.
    first = _StreamScriptedAdapter("a-model", [[RateLimited("429")], [RateLimited("429 again")]])
    second = _StreamScriptedAdapter("b-model", [[AnswerCompleted(answer=_answer("from fallback"))]])
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert first.stream_calls == 2
    assert second.stream_calls == 1
    assert isinstance(events[-1], AnswerCompleted)
    assert events[-1].answer.profile_id == "fallback"


def test_a_pre_delta_rejection_crosses_only_to_a_different_kind() -> None:
    first = _StreamScriptedAdapter("a-model", [[RequestRejected("400")]])
    second = _StreamScriptedAdapter("b-model", [[AnswerCompleted(answer=_answer("other shape"))]])
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert second.stream_calls == 1
    assert isinstance(events[-1], AnswerCompleted)


# --- The not-found sentinel never rides a fail-over ---------------------------------


def test_a_not_found_completion_is_terminal_and_never_fails_over() -> None:
    # A completed not-found (the sentinel reply, no deltas) is an honest outcome,
    # not a failure: the router forwards it alone and never lets the next entry
    # silently answer instead.
    not_found = GeneratedAnswer(text="", cited_chunk_ids=(), model="a-model", found=False)
    first = _StreamScriptedAdapter("a-model", [[AnswerCompleted(answer=not_found)]])
    second = _StreamScriptedAdapter("b-model", [[AnswerCompleted(answer=_answer("x"))]])
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert [type(event) for event in events] == [AnswerCompleted]
    assert isinstance(events[0], AnswerCompleted)
    assert not events[0].answer.found
    assert events[0].answer.profile_id == "primary"
    assert second.stream_calls == 0


def test_a_sentinel_first_delta_commits_the_stream_without_failover() -> None:
    # The hold-back that keeps the sentinel from the client lives above the
    # router; the router's duty is to not act on the text: a first delta — even
    # the sentinel itself — commits the stream, and nothing from another entry
    # may follow it.
    sentinel_reply = GeneratedAnswer(text=SENTINEL, cited_chunk_ids=(), model="a", found=False)
    first = _StreamScriptedAdapter(
        "a-model", [[AnswerTextDelta(text=SENTINEL), AnswerCompleted(answer=sentinel_reply)]]
    )
    second = _StreamScriptedAdapter("b-model", [[AnswerCompleted(answer=_answer("x"))]])
    router = _stream_router(_entry("primary", first), _entry("fallback", second, kind="local"))

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert [type(event) for event in events] == [AnswerTextDelta, AnswerCompleted]
    assert second.stream_calls == 0


def test_closing_the_router_stream_closes_the_serving_candidate() -> None:
    # Closing the iterator early cancels the underlying generation (port
    # contract): the router must pass the close through to the serving entry's
    # stream so a client disconnect never leaks a provider generation.
    first = _StreamScriptedAdapter(
        "a-model", [[AnswerTextDelta(text="partial"), AnswerTextDelta(text=" more")]]
    )
    router = _stream_router(_entry("primary", first))

    stream = router.generate_stream(mode=_MODE, message="q", evidence=[])
    next(stream)  # one delta out
    stream.close()

    assert first.closed is True


# --- ROUTE-03: mode-scoped eligibility, honest failure before any provider touch ----


def test_an_ask_turn_on_an_ask_disabled_chain_fails_with_zero_adapter_calls() -> None:
    # Every profile ask-ineligible: the only honest outcome is the turn failure
    # the application already maps to its error envelope — raised before any
    # provider is touched, so the zero-calls sensor stays at zero.
    disabled = _ScriptedAdapter("a-model", [])
    router = RoutingGenerationAdapter((_entry("quiet", disabled, ask=False),))

    with pytest.raises(RuntimeError, match="no generation profile is enabled"):
        router.generate(mode=_MODE, message="q", evidence=[])

    assert disabled.calls == 0


def test_an_ask_turn_skips_ask_disabled_entries_to_the_first_enabled_one() -> None:
    disabled = _ScriptedAdapter("a-model", [])
    enabled = _ScriptedAdapter("b-model", [_answer("from the ask-enabled entry")])
    router = RoutingGenerationAdapter(
        (_entry("quiet", disabled, ask=False), _entry("loud", enabled, kind="local"))
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from the ask-enabled entry"
    assert answer.profile_id == "loud"
    assert disabled.calls == 0


def test_a_teach_turn_routes_only_over_teach_enabled_entries() -> None:
    ask_only = _ScriptedAdapter("a-model", [])
    teachable = _ScriptedAdapter("b-model", [_answer("the teachable entry")])
    router = RoutingGenerationAdapter(
        (_entry("ask-only", ask_only, teach=False), _entry("teachable", teachable, kind="local"))
    )

    answer = router.generate(mode=MODE_TEACH, message="q", evidence=[])

    assert answer.text == "the teachable entry"
    assert answer.profile_id == "teachable"
    assert ask_only.calls == 0


def test_a_teach_turn_on_a_teach_disabled_chain_fails_honest() -> None:
    disabled = _ScriptedAdapter("a-model", [])
    router = RoutingGenerationAdapter((_entry("quiet", disabled, teach=False),))

    with pytest.raises(RuntimeError, match="mode 'teach'"):
        router.generate(mode=MODE_TEACH, message="q", evidence=[])

    assert disabled.calls == 0
