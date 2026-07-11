"""T2 gate — structure-first chunk packing (unit, pure function).

Derived from CORP-05 / A-5: whole blocks pack to ``<= max_chars`` joined by
``\\n\\n``; a single block over the cap splits at sentence boundaries with a hard
character fallback so the cap is absolute; empty/whitespace blocks are skipped;
chunk indices are contiguous from 0; each chunk carries its section's
``section_path``/``anchor`` and a null ``page_span`` (A-9).
"""

from __future__ import annotations

from app.application.chunking import pack_chunks

_PATH = ("Meditations", "Book I")
_ANCHOR = "book01.xhtml#b1"


def _pack(blocks: list[str], *, max_chars: int):  # noqa: ANN202
    return pack_chunks(
        blocks, max_chars=max_chars, section_path=_PATH, anchor=_ANCHOR
    )


def test_packs_whole_blocks_under_cap_joined_by_blank_line() -> None:
    # "alpha\n\nbeta\n\ngamma" == 18 chars <= 20 → a single packed chunk.
    chunks = _pack(["alpha", "beta", "gamma"], max_chars=20)

    assert len(chunks) == 1
    assert chunks[0].text == "alpha\n\nbeta\n\ngamma"
    assert chunks[0].index == 0


def test_starts_new_chunk_when_next_block_would_exceed_cap() -> None:
    # "alpha\n\nbeta" == 11 <= 12; adding "\n\ngamma" would reach 18 > 12.
    chunks = _pack(["alpha", "beta", "gamma"], max_chars=12)

    assert [c.text for c in chunks] == ["alpha\n\nbeta", "gamma"]
    assert all(len(c.text) <= 12 for c in chunks)


def test_packs_up_to_exactly_max_chars_inclusive() -> None:
    # 9 + len("\n\n") + 9 == 20 == max → still one chunk (boundary is inclusive).
    chunks = _pack(["a" * 9, "b" * 9], max_chars=20)

    assert len(chunks) == 1
    assert len(chunks[0].text) == 20


def test_single_block_at_exactly_max_is_not_split() -> None:
    chunks = _pack(["x" * 20], max_chars=20)

    assert len(chunks) == 1
    assert chunks[0].text == "x" * 20


def test_oversized_block_splits_at_sentence_boundaries() -> None:
    # "Aaa. Bbb. Ccc." == 14 > 8 → sentence split; each sentence alone is <= 8.
    chunks = _pack(["Aaa. Bbb. Ccc."], max_chars=8)

    assert [c.text for c in chunks] == ["Aaa.", "Bbb.", "Ccc."]
    assert all(len(c.text) <= 8 for c in chunks)


def test_sentence_free_oversized_block_hard_splits_to_respect_cap() -> None:
    # No sentence boundary → hard character slices; the cap is still absolute.
    chunks = _pack(["x" * 25], max_chars=10)

    assert [c.text for c in chunks] == ["x" * 10, "x" * 10, "x" * 5]
    assert all(len(c.text) <= 10 for c in chunks)
    assert "".join(c.text for c in chunks) == "x" * 25


def test_empty_and_whitespace_blocks_are_skipped() -> None:
    chunks = _pack(["alpha", "", "   ", "\n\t", "beta"], max_chars=100)

    assert len(chunks) == 1
    assert chunks[0].text == "alpha\n\nbeta"


def test_all_blocks_empty_yields_no_chunks() -> None:
    assert _pack(["", "   ", "\n"], max_chars=100) == ()
    assert _pack([], max_chars=100) == ()


def test_carries_section_path_anchor_and_null_page_span() -> None:
    chunks = _pack(["Aaa. Bbb. Ccc.", "gamma"], max_chars=8)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.section_path == _PATH
        assert chunk.anchor == _ANCHOR
        assert chunk.page_span is None


def test_indices_are_contiguous_from_zero() -> None:
    # Three small blocks each over the join cap → three ordered chunks.
    chunks = _pack(["alpha", "beta", "gamma"], max_chars=5)

    assert [c.index for c in chunks] == [0, 1, 2]
