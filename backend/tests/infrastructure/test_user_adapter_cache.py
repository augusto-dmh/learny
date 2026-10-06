"""The per-learner adapter cache: keyed on the key write, bounded, and expiring.

A learner-keyed adapter holds one learner's key, so its cache must key on the
fingerprint of the credential row it was built from: two learners' keys never
share an entry, and a new key write never resolves the old adapter. The cache
holds at most its bound (256 by default) entries, evicting the least recently
used, and an entry older than its TTL is rebuilt on the next lookup.
"""

from __future__ import annotations

from app.infrastructure.answering.user_adapters import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_TTL_SECONDS,
    UserAdapterCache,
    UserAdapterKey,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Built:
    """A stand-in adapter that remembers which build produced it."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.model = "m"


def _key(fingerprint: str, profile_id: str = "byok-claude") -> UserAdapterKey:
    return UserAdapterKey(
        provider="anthropic", profile_id=profile_id, model="claude-x", fingerprint=fingerprint
    )


def test_keys_on_fingerprint() -> None:
    cache = UserAdapterCache()
    builds: list[str] = []

    def _build(label: str):  # noqa: ANN202
        def _make() -> _Built:
            builds.append(label)
            return _Built(label)

        return _make

    learner_a = cache.get_or_build(_key("fp-a"), _build("a"))
    learner_b = cache.get_or_build(_key("fp-b"), _build("b"))
    learner_a_again = cache.get_or_build(_key("fp-a"), _build("a-again"))

    # Two fingerprints on the same provider, profile and model: two distinct entries.
    assert learner_a is not learner_b
    assert learner_a.label == "a" and learner_b.label == "b"
    assert len(cache) == 2
    # The same fingerprint is a hit: no second build.
    assert learner_a_again is learner_a
    assert builds == ["a", "b"]
    # A new key write (new fingerprint) never resolves the old adapter.
    replaced = cache.get_or_build(_key("fp-a2"), _build("a2"))
    assert replaced is not learner_a and replaced.label == "a2"


def test_keys_on_fingerprint_and_profile_together() -> None:
    cache = UserAdapterCache()

    ask = cache.get_or_build(_key("fp", "byok-ask"), lambda: _Built("ask"))
    explain = cache.get_or_build(_key("fp", "byok-explain"), lambda: _Built("explain"))

    assert ask is not explain
    assert len(cache) == 2


def test_lru_bound_and_ttl_evicts_the_least_recently_used() -> None:
    assert DEFAULT_MAX_ENTRIES == 256
    cache = UserAdapterCache()
    for i in range(DEFAULT_MAX_ENTRIES):
        cache.get_or_build(_key(f"fp-{i}"), lambda i=i: _Built(str(i)))
    # Touch the oldest so it becomes the most recently used.
    first = cache.get_or_build(_key("fp-0"), lambda: _Built("rebuilt-0"))
    assert first.label == "0"

    cache.get_or_build(_key("fp-new"), lambda: _Built("new"))

    assert len(cache) == DEFAULT_MAX_ENTRIES
    keys = cache.keys()
    assert _key("fp-1") not in keys  # the least recently used went
    assert _key("fp-0") in keys and _key("fp-new") in keys
    rebuilt = cache.get_or_build(_key("fp-1"), lambda: _Built("rebuilt-1"))
    assert rebuilt.label == "rebuilt-1"


def test_lru_bound_and_ttl_rebuilds_an_expired_entry() -> None:
    assert DEFAULT_TTL_SECONDS == 15 * 60
    clock = _Clock()
    cache = UserAdapterCache(clock=clock)
    original = cache.get_or_build(_key("fp"), lambda: _Built("original"))

    clock.now += DEFAULT_TTL_SECONDS - 1
    assert cache.get_or_build(_key("fp"), lambda: _Built("early")) is original

    clock.now += 2  # now past the TTL since the build
    rebuilt = cache.get_or_build(_key("fp"), lambda: _Built("rebuilt"))

    assert rebuilt is not original and rebuilt.label == "rebuilt"
    assert len(cache) == 1


def test_lru_bound_and_ttl_holds_a_small_bound_too() -> None:
    cache = UserAdapterCache(max_entries=2)
    cache.get_or_build(_key("a"), lambda: _Built("a"))
    cache.get_or_build(_key("b"), lambda: _Built("b"))
    cache.get_or_build(_key("c"), lambda: _Built("c"))

    assert cache.keys() == (_key("b"), _key("c"))


def test_a_build_that_yields_nothing_is_not_cached() -> None:
    cache = UserAdapterCache()

    assert cache.get_or_build(_key("fp"), lambda: None) is None
    assert len(cache) == 0
    assert cache.get_or_build(_key("fp"), lambda: _Built("later")).label == "later"


def test_clear_drops_every_entry() -> None:
    cache = UserAdapterCache()
    cache.get_or_build(_key("fp"), lambda: _Built("x"))

    cache.clear()

    assert len(cache) == 0
