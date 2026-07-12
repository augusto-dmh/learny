"""Deterministic, network-free answer adapter (implements ``AnswerGenerationPort``).

The default answer generator (AD-024, mirror of the embedding adapter's AD-019):
pure Python, no network, no provider SDK. It composes an extractive answer from
the retrieved evidence's own snippets — the top ``_MAX_SNIPPETS`` in retrieval
rank order, joined by blank lines — and cites exactly those chunks, so the answer
is grounded by construction. Same question and evidence → identical result
(deterministic), keeping golden-fixture answers stable.

Swapping in a real provider later is an adapter change behind
``AnswerGenerationPort``, never a domain change (ADR-0007/0009).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.entities import Evidence, GeneratedAnswer

# Model identity surfaced on every result's diagnostics (QA-04); distinguishes
# this extractive default from a future provider adapter.
_MODEL = "local-extractive"

# How many top-ranked snippets the extractive answer draws on. Adapter-local
# prompt-shaping detail, not product configuration (design §Tech Decisions).
_MAX_SNIPPETS = 3


class DeterministicAnswerAdapter:
    """``AnswerGenerationPort`` implementation — extractive, evidence-only.

    Needs no provider client: constructed with no arguments and makes no network
    call, so the answer path is testable offline (AD-024).
    """

    # Stable model identity, readable without a ``generate`` call so the Q&A
    # service can surface it on the not-found-on-empty-evidence response where the
    # port is deliberately not invoked (QA-04/QA-13).
    model = _MODEL

    def generate(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> GeneratedAnswer:
        """Compose an answer from the top evidence snippets, citing those chunks.

        Empty evidence → ``found=False`` empty result (defensive; the service
        short-circuits before calling this). Otherwise the answer is the top
        ``min(_MAX_SNIPPETS, len(evidence))`` snippets in retrieval order joined
        by blank lines, citing exactly those chunk ids, ``found=True``.
        """
        if not evidence:
            return GeneratedAnswer(
                text="", cited_chunk_ids=(), model=self.model, found=False
            )
        selected = list(evidence[:_MAX_SNIPPETS])
        text = "\n\n".join(item.snippet for item in selected)
        cited = tuple(item.chunk_id for item in selected)
        return GeneratedAnswer(
            text=text, cited_chunk_ids=cited, model=self.model, found=True
        )
