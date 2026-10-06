"""The per-learner adapter cache (ADR-0033 point 7).

House chains are cached per process by ``lru_cache`` because they derive from
settings alone. A learner-keyed adapter carries one learner's key, so it can
never live there: it would serve that key to everyone. This cache holds built
learner-keyed adapters instead, keyed on ``(provider, profile id, model,
fingerprint)``. The fingerprint is read from the learner's live credential row,
and it changes on every write, so a replaced or deleted key can never resolve
an entry again.

The cache is bounded (least-recently-used eviction) and every entry expires
after a TTL, so a process never accumulates adapters for keys nobody uses. It
is thread-safe: FastAPI runs sync dependencies on a thread pool.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.ports import GenerationPort

#: Landing door 4: at most 256 built adapters per process, each for 15 minutes.
DEFAULT_MAX_ENTRIES = 256
DEFAULT_TTL_SECONDS = 15 * 60.0


@dataclass(frozen=True)
class UserAdapterKey:
    """Which adapter an entry is: the profile it serves and the key write it holds."""

    provider: str
    profile_id: str
    model: str
    fingerprint: str


class UserAdapterCache:
    """A bounded LRU with a TTL over built learner-keyed adapters."""

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("the adapter cache needs room for at least one entry")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[UserAdapterKey, tuple[float, GenerationPort]] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __repr__(self) -> str:
        return f"UserAdapterCache(entries={len(self)}, max_entries={self._max_entries})"

    def get_or_build(
        self,
        key: UserAdapterKey,
        build: Callable[[], GenerationPort | None],
    ) -> GenerationPort | None:
        """Return the live entry for ``key``, building (and caching) it on a miss.

        An entry older than the TTL counts as a miss and is rebuilt. ``build``
        returning ``None`` (the key could not be opened) caches nothing, so the
        next lookup tries again rather than remembering a failure.
        """
        now = self._clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                built_at, adapter = cached
                if now - built_at < self._ttl_seconds:
                    self._entries.move_to_end(key)
                    return adapter
                del self._entries[key]
            adapter = build()
            if adapter is None:
                return None
            self._entries[key] = (now, adapter)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            return adapter

    def keys(self) -> tuple[UserAdapterKey, ...]:
        """The cached keys, least recently used first (introspection for tests)."""
        with self._lock:
            return tuple(self._entries)

    def clear(self) -> None:
        """Drop every entry (settings redeclared, or a test boundary)."""
        with self._lock:
            self._entries.clear()
