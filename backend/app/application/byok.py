"""The learner-side BYOK policy (learner keys on a hosted instance).

Where :class:`~app.application.budget.DailyBudget` guards the operator's
wallet, this service guards the learner's own: a soft monthly budget that
pauses their key when the month's estimated cost reaches it, and a per-corpus
prompt-token ceiling that bounds bulk pumping of one book through one key.
Both rules run in the application layer beside the daily budget, over their
own ledgers, with the same shape as everything here: check before the provider
is touched, record only what a successful call actually reported.

Every rule is scoped to calls the learner's own key would serve
(``user_keyed``): a house-served call is the operator's money under the house
rails, and never lands in — or is stopped by — either ledger. The two refusals
carry machine codes (``byok_budget``, ``byok_corpus_limit``) beside their
English copy, because the frontend renders catalog copy keyed on the code and
never the backend ``detail``.

Framework-free (ADR-0007/0009): repositories arrive as ports, time from the
injected ``Clock``, and the price estimate as the composition root's bound
:meth:`~app.application.budget.DailyBudget.estimate_micros` — one price list
serving both the operator's debits and the learner's estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.errors import ByokBudgetExhausted, ByokCorpusLimitExhausted
from app.domain.entities import TokenUsage
from app.domain.ports import ByokCorpusLedger, ByokMonthLedger, ByokSettingsStore, Clock

#: ``YYYY-MM``, the UTC calendar month the ledgers and the budget live in.
_MONTH_FORMAT = "%Y-%m"

#: The budget refusal copy. Names whose budget it is and where it changes — the
#: learner can un-pause their own key, which is what makes the budget soft.
BUDGET_COPY = (
    "You've reached your own monthly spending budget for your API key, so your "
    "key is paused for the rest of this month. You can raise or clear it in "
    "Account."
)

#: The per-book ceiling refusal copy. Names the limit's scope so the learner can
#: move to another book (or wait for the month) rather than guessing at a meter.
CORPUS_COPY = (
    "This book has reached the monthly prompt limit for your own API key, so "
    "turns on it are paused for the rest of this month. Other books are "
    "unaffected."
)


def _period(clock: Clock) -> str:
    return clock.now().strftime(_MONTH_FORMAT)


class ByokPolicy:
    """Assert the learner-side rails before a user-keyed call; record after it.

    ``assert_turn`` runs in the preflight, before retrieval or generation: a
    refused turn touches no provider, no ledger, and no conversation. The
    monthly budget trips when the month's estimated cost is at or above the
    learner's stored budget; the corpus ceiling trips when the month-to-date
    prompt tokens for the turn's source are at or above the operator's cap — a
    cap of ``0`` disables it. ``record_turn`` runs after a successful call and
    accumulates the call's actual reported usage and estimated cost into the
    monthly ledger and, when the call targeted a source, its per-corpus ledger.
    """

    def __init__(
        self,
        *,
        months: ByokMonthLedger,
        corpus: ByokCorpusLedger,
        settings: ByokSettingsStore,
        clock: Clock,
        corpus_cap_tokens: int,
        estimate: Callable[[TokenUsage | None, str | None], int],
    ) -> None:
        if corpus_cap_tokens < 0:
            raise ValueError("the corpus prompt-token ceiling cannot be negative")
        self._months = months
        self._corpus = corpus
        self._settings = settings
        self._clock = clock
        self._corpus_cap_tokens = corpus_cap_tokens
        self._estimate = estimate

    def assert_turn(self, user_id: UUID, *, user_keyed: bool, source_id: UUID | None) -> None:
        """Refuse a user-keyed turn a learner-side rail has paused; pass everything else.

        A call the learner's key does not serve is invisible here — the house
        rails govern it, as ever. The budget is read before the ledgers: a learner
        with no budget set and an empty month does the cheapest possible walk.
        """
        if not user_keyed:
            return
        month = _period(self._clock)
        stored = self._settings.get(user_id)
        budget = stored.monthly_budget_usd_micros if stored is not None else None
        if budget is not None:
            usage = self._months.get_for_month(user_id, month)
            if usage is not None and usage.cost_usd_micros >= budget:
                raise ByokBudgetExhausted(BUDGET_COPY)
        if self._corpus_cap_tokens > 0 and source_id is not None:
            corpus = self._corpus.get_for_month(user_id, source_id, month)
            if corpus is not None and corpus.input_tokens >= self._corpus_cap_tokens:
                raise ByokCorpusLimitExhausted(CORPUS_COPY)

    def record_turn(
        self,
        user_id: UUID,
        *,
        user_keyed: bool,
        source_id: UUID | None,
        usage: TokenUsage | None,
        profile_id: str | None,
    ) -> None:
        """Accumulate a successful user-keyed call's actual usage and estimated cost.

        Only a call that reported usage writes anything — a zero debit never
        mints a row, matching the daily ledger's rule. The estimate prices the
        serving profile's catalog; the corpus ledger counts the same call's
        input tokens against the book the call was about.
        """
        if not user_keyed or usage is None:
            return
        month = _period(self._clock)
        cost_usd_micros = self._estimate(usage, profile_id)
        self._months.record(
            user_id,
            month,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd_micros=cost_usd_micros,
        )
        if source_id is not None:
            self._corpus.record(user_id, source_id, month, input_tokens=usage.input_tokens)

    def month_usage(self, user_id: UUID) -> tuple[str, int, int, int]:
        """The caller's month-to-date ``(period, input, output, cost)`` for the account view.

        A month with no user-keyed call reads as zeros, not an absent row.
        """
        month = _period(self._clock)
        usage = self._months.get_for_month(user_id, month)
        if usage is None:
            return month, 0, 0, 0
        return month, usage.input_tokens, usage.output_tokens, usage.cost_usd_micros

    def stored_budget(self, user_id: UUID) -> int | None:
        """The learner's stored monthly budget, or ``None`` while none is set."""
        stored = self._settings.get(user_id)
        return stored.monthly_budget_usd_micros if stored is not None else None
