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
    MODE_ANSWER,
    MODE_TEACH,
    SENTINEL,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    GeneratedAnswer,
)
from app.infrastructure.answering import order_learner_profiles
from app.infrastructure.answering.routing import (
    ChainEntry,
    RoutingGenerationAdapter,
    _next_index,
)
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


# --- Learner-keyed entries: lead, never fall over into the house (ADR-0033) ----------
#
# A learner who holds a key has user-keyed entries leading their chain. Every
# fail-over rule still applies among those entries, but no failure ever walks
# from a user-keyed entry to a house-keyed one: a broken learner key surfaces as
# the honest generation failure instead of being silently billed to the house.
# A mode that no user-keyed entry is eligible for is served by the house, as
# for a learner without a key.


def _keyed(
    id: str,  # noqa: A002 — the settings field is named ``id``
    adapter: object,
    *,
    kind: str = "anthropic",
    ask: bool = True,
    teach: bool = True,
) -> ChainEntry:
    return ChainEntry(
        adapter=adapter,  # type: ignore[arg-type]
        profile=_profile(id, kind, ask=ask, teach=teach),
        user_keyed=True,
    )


_FAILURES = [
    pytest.param(RequestRejected("401 invalid x-api-key"), id="rejected"),
    pytest.param(ProviderUnavailable("503"), id="unavailable"),
    pytest.param(Timeout("timed out"), id="timeout"),
    pytest.param(RateLimited("429"), id="rate_limited"),
]


def _fails_always(model: str, error: Exception) -> _ScriptedAdapter:
    return _ScriptedAdapter(model, [error, error, error, error])


@pytest.mark.parametrize("error", _FAILURES)
def test_never_falls_from_user_key_to_house_in_a_mixed_chain(error: Exception) -> None:
    # Two user-keyed entries of different kinds (so a rejection may cross between
    # them), then house entries of yet other kinds that the walk could reach if
    # the owner rule were missing.
    keyed_a = _fails_always("keyed-a", error)
    keyed_b = _fails_always("keyed-b", error)
    house_local = _ScriptedAdapter("house-local", [_answer("house local")])
    house_compat = _ScriptedAdapter("house-compat", [_answer("house compat")])
    router = RoutingGenerationAdapter(
        (
            _keyed("byok-a", keyed_a, kind="anthropic"),
            _keyed("byok-b", keyed_b, kind="openai-compatible"),
            _entry("house-local", house_local, kind="local"),
            _entry("house-compat", house_compat, kind="openai-compatible"),
        ),
        rate_retry_delay=0.0,
    )

    with pytest.raises(type(error)):
        router.generate(mode=_MODE, message="q", evidence=[])

    assert keyed_a.calls >= 1
    assert house_local.calls == 0
    assert house_compat.calls == 0


@pytest.mark.parametrize("error", _FAILURES)
def test_never_falls_from_user_key_to_house_behind_the_house_port(error: Exception) -> None:
    # The composition shape: the learner's router holds only user-keyed entries
    # and the house chain rides beside it as a port. A failure among the keyed
    # entries never reaches it.
    keyed = _fails_always("keyed", error)
    house_entry = _ScriptedAdapter("house", [_answer("house")])
    house = RoutingGenerationAdapter((_entry("house", house_entry, kind="local"),))
    router = RoutingGenerationAdapter((_keyed("byok", keyed),), rate_retry_delay=0.0, house=house)

    with pytest.raises(type(error)):
        router.generate(mode=_MODE, message="q", evidence=[])

    assert keyed.calls >= 1
    assert house_entry.calls == 0


def test_never_falls_from_user_key_to_house_while_fail_over_among_keyed_entries_holds() -> None:
    keyed_a = _ScriptedAdapter("keyed-a", [ProviderUnavailable("503")])
    keyed_b = _ScriptedAdapter("keyed-b", [_answer("from the second learner entry")])
    house = _ScriptedAdapter("house", [_answer("house")])
    router = RoutingGenerationAdapter(
        (
            _keyed("byok-a", keyed_a),
            _keyed("byok-b", keyed_b),
            _entry("house", house, kind="local"),
        ),
        rate_retry_delay=0.0,
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "from the second learner entry"
    assert answer.profile_id == "byok-b"
    assert answer.user_keyed is True
    assert house.calls == 0


@pytest.mark.parametrize("error", _FAILURES)
def test_never_falls_from_user_key_to_house_before_the_first_stream_delta(
    error: Exception,
) -> None:
    keyed = _StreamScriptedAdapter("keyed", [[error], [error]])
    house = _StreamScriptedAdapter("house", [[AnswerCompleted(answer=_answer("house"))]])
    router = RoutingGenerationAdapter(
        (_keyed("byok", keyed), _entry("house", house, kind="local")),
        rate_retry_delay=0.0,
    )

    with pytest.raises(type(error)):
        _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    assert keyed.stream_calls >= 1
    assert house.stream_calls == 0


def test_uncovered_mode_served_by_house_entries_in_a_mixed_chain() -> None:
    keyed = _ScriptedAdapter("keyed", [])
    house = _ScriptedAdapter("house", [_answer("house answer")])
    router = RoutingGenerationAdapter(
        (_keyed("byok", keyed, ask=False), _entry("house", house, kind="local"))
    )

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.text == "house answer"
    assert answer.profile_id == "house"
    assert answer.user_keyed is False
    assert keyed.calls == 0


def test_uncovered_mode_served_by_house_port_exactly_as_the_house_answers() -> None:
    keyed = _ScriptedAdapter("keyed", [])
    house_entry = _ScriptedAdapter("house", [_answer("house answer")])
    house = RoutingGenerationAdapter((_entry("house-primary", house_entry, kind="local"),))
    router = RoutingGenerationAdapter((_keyed("byok", keyed, teach=False),), house=house)

    answer = router.generate(mode=MODE_TEACH, message="q", evidence=[])

    assert answer.text == "house answer"
    assert answer.profile_id == "house-primary"
    assert answer.user_keyed is False
    assert keyed.calls == 0


def test_uncovered_mode_served_by_house_port_when_streaming() -> None:
    keyed = _StreamScriptedAdapter("keyed", [])
    house_entry = _StreamScriptedAdapter(
        "house", [[AnswerTextDelta(text="hi"), AnswerCompleted(answer=_answer("hi"))]]
    )
    house = RoutingGenerationAdapter((_entry("house-primary", house_entry, kind="local"),))
    router = RoutingGenerationAdapter((_keyed("byok", keyed, ask=False),), house=house)

    events = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))

    completed = events[-1]
    assert isinstance(completed, AnswerCompleted)
    assert completed.answer.profile_id == "house-primary"
    assert completed.answer.user_keyed is False
    assert keyed.stream_calls == 0


def test_a_user_keyed_answer_is_stamped_as_learner_paid() -> None:
    keyed = _ScriptedAdapter("keyed", [_answer("learner answer")])
    house = _ScriptedAdapter("house", [])
    router = RoutingGenerationAdapter((_keyed("byok", keyed), _entry("house", house, kind="local")))

    answer = router.generate(mode=_MODE, message="q", evidence=[])

    assert answer.profile_id == "byok"
    assert answer.user_keyed is True
    assert house.calls == 0


def test_a_house_answer_is_never_stamped_as_learner_paid() -> None:
    house = _ScriptedAdapter("house", [_answer("house answer")])
    router = RoutingGenerationAdapter((_entry("house", house),))

    assert router.generate(mode=_MODE, message="q", evidence=[]).user_keyed is False


def test_a_streamed_user_keyed_answer_is_stamped_as_learner_paid() -> None:
    # The streamed debit prices the completed answer through this stamp, so a
    # learner-keyed stream must come out learner-paid, as a buffered call does.
    keyed = _StreamScriptedAdapter(
        "keyed", [[AnswerTextDelta(text="hi"), AnswerCompleted(answer=_answer("hi"))]]
    )
    house = _StreamScriptedAdapter("house", [])
    router = RoutingGenerationAdapter((_keyed("byok", keyed), _entry("house", house, kind="local")))

    completed = _collect(router.generate_stream(mode=_MODE, message="q", evidence=[]))[-1]

    assert isinstance(completed, AnswerCompleted)
    assert completed.answer.profile_id == "byok"
    assert completed.answer.user_keyed is True
    assert house.stream_calls == 0


@pytest.mark.parametrize("error", _FAILURES)
def test_the_walk_never_steps_from_a_user_keyed_entry_onto_a_house_one(error: Exception) -> None:
    # The serving slice is never mixed today; this pins the guard for a walk that is.
    mixed = (
        _keyed("byok", _ScriptedAdapter("byok", [])),
        _entry("house", _ScriptedAdapter("house", []), kind="local"),
    )
    # A different kind next, so even a rejection would cross to it.
    house_only = (
        _entry("house-a", _ScriptedAdapter("a", [])),
        _entry("house-b", _ScriptedAdapter("b", []), kind="local"),
    )

    assert _next_index(mixed, 0, error, {0}) is None
    assert _next_index(house_only, 0, error, {0}) == 1


# --- Which bound profiles a learner's keys serve, and in what order -----------------


def _bound(id: str, provider: str | None) -> GenerationProfileSettings:  # noqa: A002
    return _profile(id).model_copy(update={"user_key_provider": provider})


_REGISTRY = (
    _bound("house", None),
    _bound("byok-a", "anthropic"),
    _bound("byok-o", "openai"),
    _bound("byok-a2", "anthropic"),
)


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        pytest.param(None, ["byok-a", "byok-a2"], id="no-lead-registry-order"),
        pytest.param("byok-a2", ["byok-a2", "byok-a"], id="bound-lead-moves-first"),
        pytest.param("house", ["byok-a", "byok-a2"], id="unbound-lead-ignored"),
        pytest.param("byok-o", ["byok-a", "byok-a2"], id="other-provider-lead-ignored"),
        pytest.param("missing", ["byok-a", "byok-a2"], id="unknown-lead-ignored"),
    ],
)
def test_learner_profiles_follow_registry_order_with_only_a_bound_lead_moved(
    lead: str | None, expected: list[str]
) -> None:
    ordered = order_learner_profiles(_REGISTRY, frozenset({"anthropic"}), lead=lead)

    assert [p.id for p in ordered] == expected


# --- Response language: forwarded to whichever adapter serves ---------------------
#
# The router owns fail-over policy and nothing about prompts, so the learner's
# response language must reach the entry that answers unchanged — the first one,
# a fail-over candidate after a pre-delta failure, or the house chain a learner's
# chain rides beside — on the buffered and the streamed path alike.


class _RecordingAdapter:
    """A port double that records each call's ``response_language`` and serves.

    ``fail_first`` makes its first call (buffered or streamed) raise a pre-delta
    timeout, so a router fails over past it.
    """

    def __init__(self, model: str, *, fail_first: bool = False) -> None:
        self.model = model
        self._fail = fail_first
        self.languages: list[object] = []

    def _maybe_fail(self) -> None:
        if self._fail:
            self._fail = False
            raise Timeout("hung before speaking")

    def generate(self, **kwargs: object) -> GeneratedAnswer:
        self.languages.append(kwargs.get("response_language", "<missing>"))
        self._maybe_fail()
        return GeneratedAnswer(text="ok", cited_chunk_ids=(), model=self.model, found=True)

    def generate_stream(self, **kwargs: object) -> Iterator[AnswerStreamEvent]:
        self.languages.append(kwargs.get("response_language", "<missing>"))
        return self._events()

    def _events(self) -> Iterator[AnswerStreamEvent]:
        # A stream fails while it is iterated, like the real adapters' streams.
        self._maybe_fail()
        answer = GeneratedAnswer(text="ok", cited_chunk_ids=(), model=self.model, found=True)
        yield AnswerTextDelta(text="ok")
        yield AnswerCompleted(answer=answer)


def _call(router: RoutingGenerationAdapter, *, stream: bool, mode: str, language: str | None):
    kwargs = {
        "message": "q",
        "mode": mode,
        "evidence": (),
        "response_language": language,
    }
    if stream:
        return list(router.generate_stream(**kwargs))[-1].answer
    return router.generate(**kwargs)


@pytest.mark.parametrize("language", ["pt-BR", None])
@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
def test_response_language_is_forwarded(stream: bool, language: str | None) -> None:
    # The primary fails before speaking; the fallback serves. Both saw the value.
    primary = _RecordingAdapter("a-model", fail_first=True)
    fallback = _RecordingAdapter("b-model")
    router = RoutingGenerationAdapter(
        (
            ChainEntry(adapter=primary, profile=_profile("primary")),
            ChainEntry(adapter=fallback, profile=_profile("fallback", "local")),
        ),
        rate_retry_delay=0.0,
    )

    served = _call(router, stream=stream, mode=MODE_ANSWER, language=language)

    assert served.profile_id == "fallback"
    assert primary.languages == [language]
    assert fallback.languages == [language]

    # A learner chain with no entry for the mode hands the turn to the house
    # chain, response language included.
    house = _RecordingAdapter("house-model")
    learner = _RecordingAdapter("learner-model")
    beside = RoutingGenerationAdapter(
        (ChainEntry(adapter=learner, profile=_profile("mine", teach=False)),),
        rate_retry_delay=0.0,
        house=house,
    )

    _call(beside, stream=stream, mode=MODE_TEACH, language=language)

    assert learner.languages == []
    assert house.languages == [language]


# --- A learner-keyed adapter is built on the profile's host only --------------------


def test_user_keyed_adapter_builds_on_the_profile_host_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter a learner-keyed turn builds sends the key to the bound
    profile's declared host and nothing else: construction takes the profile and
    the key, so no request-supplied endpoint can enter."""
    import anthropic
    import openai

    from app.core.config import Settings
    from app.infrastructure.answering import build_user_keyed_adapter

    built: list[dict[str, object]] = []

    class _RecordingClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            built.append(kwargs)

    monkeypatch.setattr(anthropic, "Anthropic", _RecordingClient)
    monkeypatch.setattr(openai, "OpenAI", _RecordingClient)

    compat = GenerationProfileSettings(
        id="byok-gpt",
        kind="openai-compatible",
        model="gpt-x",
        base_url="https://api.openai.com/v1",
        max_tokens=64,
        price_input_usd_per_million_tokens=1.0,
        price_output_usd_per_million_tokens=1.0,
        price_cache_read_usd_per_million_tokens=0.1,
        price_cache_creation_usd_per_million_tokens=1.25,
        grounding="prompt-cited",
        ask_enabled=True,
        teach_enabled=False,
        user_key_provider="openai",
    )
    adapter = build_user_keyed_adapter(compat, Settings(_env_file=None), api_key="sk-test-key")
    assert adapter is not None
    client = adapter._get_client()  # the lazily built SDK client, forced for the assertion
    assert client.kwargs["base_url"] == "https://api.openai.com/v1"  # type: ignore[attr-defined]
    assert client.kwargs["api_key"] == "sk-test-key"  # type: ignore[attr-defined]

    native = GenerationProfileSettings(
        id="byok-claude",
        kind="anthropic",
        model="claude-x",
        max_tokens=64,
        price_input_usd_per_million_tokens=3.0,
        price_output_usd_per_million_tokens=15.0,
        price_cache_read_usd_per_million_tokens=0.3,
        price_cache_creation_usd_per_million_tokens=3.75,
        grounding="verified-spans",
        ask_enabled=True,
        teach_enabled=True,
        user_key_provider="anthropic",
    )
    adapter = build_user_keyed_adapter(native, Settings(_env_file=None), api_key="sk-ant-key")
    assert adapter is not None
    client = adapter._get_client()
    assert client.kwargs["api_key"] == "sk-ant-key"  # type: ignore[attr-defined]
    assert "base_url" not in client.kwargs  # the native host, never an override
