"""AD-027 grounding helper — empty citations still collapse at this layer.

Teach-mode persist of a citation-free non-sentinel reply is a caller carve-out
(TUTOR-05); this helper remains the Answer collapse (TUTOR-07).
"""

from __future__ import annotations

from uuid import uuid4

from app.application.grounding import ground
from app.domain.entities import Evidence, GeneratedAnswer

_MODEL = "local-extractive"


def _evidence(snippet: str = "snippet") -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        page_span=None,
        snippet=snippet,
        score=0.9,
    )


def test_ground_collapses_a_cited_empty_id_set_to_not_found() -> None:
    item = _evidence()
    generated = GeneratedAnswer(
        text="An uncited claim about the book.",
        cited_chunk_ids=(),
        model=_MODEL,
        found=True,
    )

    assert ground(generated, [item]) is None


def test_ground_collapses_found_false_even_when_text_is_present() -> None:
    item = _evidence()
    generated = GeneratedAnswer(
        text="NOT_FOUND_IN_SOURCE",
        cited_chunk_ids=(),
        model=_MODEL,
        found=False,
    )

    assert ground(generated, [item]) is None


def test_ground_keeps_text_and_cited_evidence() -> None:
    item = _evidence()
    generated = GeneratedAnswer(
        text="grounded",
        cited_chunk_ids=(item.chunk_id,),
        model=_MODEL,
        found=True,
    )

    assert ground(generated, [item]) == ("grounded", [item])
