"""Shared answer-grounding guard (ADR-0003 / AD-027).

The single home for the grounding invariant so it holds identically for the Q&A
answer path and the teaching turn path, not per-adapter goodwill. Given a port's
:class:`~app.domain.entities.GeneratedAnswer` and the retrieved evidence, it keeps
only citations that reference retrieved evidence — in evidence-rank order and
inherently deduped (evidence chunk ids are unique) — and collapses the three
not-found conditions (``found=False``, blank text, nothing survives grounding)
into a single ``None`` return. Framework-free (ADR-0007/0009): no FastAPI /
SQLAlchemy / provider-SDK type crosses this boundary.
"""

from __future__ import annotations

from app.domain.entities import Evidence, GeneratedAnswer


def ground(
    generated: GeneratedAnswer, evidence: list[Evidence]
) -> tuple[str, list[Evidence]] | None:
    """Return grounded ``(text, citations)`` or ``None`` for the not-found outcome.

    Keeps only evidence whose ``chunk_id`` the adapter cited, preserving evidence
    rank order and deduping in one pass (evidence chunk ids are unique). Returns
    ``None`` when the port reports ``found=False``, the text is blank, or no
    citation survives grounding — the explicit "the source cannot support this"
    outcome; otherwise returns the answer text with its grounded citations.
    """
    cited = set(generated.cited_chunk_ids)
    grounded = [e for e in evidence if e.chunk_id in cited]
    if not generated.found or not generated.text.strip() or not grounded:
        return None
    return generated.text, grounded
