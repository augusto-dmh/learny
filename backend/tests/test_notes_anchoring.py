"""T2 gate — pure highlight-anchor resolver (unit, NF-03).

Drives ``resolve`` over in-memory blocks, asserting the ACs and ADR edge cases:
containment with normalized offsets, not-found, first-block binding for a selection
spanning two blocks, prefix/suffix disambiguation when the quote occurs twice, and
NULL-hash tolerance (a pre-0010 unhashed block still binds).
"""

from __future__ import annotations

from app.application.anchoring import AnchorBlock, resolve


def test_resolves_a_quote_to_its_block_with_normalized_offsets() -> None:
    blocks = [AnchorBlock(ordinal=0, content_hash="h0", text="The quick brown fox")]

    binding = resolve(blocks, quote="quick brown")

    assert binding is not None
    assert binding.block_ordinal == 0
    assert binding.block_hash == "h0"
    # Offsets index the normalized ("the quick brown fox") text.
    assert (binding.start_offset, binding.end_offset) == (4, 15)


def test_matching_is_whitespace_and_case_insensitive() -> None:
    blocks = [AnchorBlock(ordinal=2, content_hash="h", text="Alpha   BETA\n gamma")]

    binding = resolve(blocks, quote="beta gamma")

    assert binding is not None
    assert binding.block_ordinal == 2
    # Normalized block text is "alpha beta gamma"; the quote starts at index 6.
    assert (binding.start_offset, binding.end_offset) == (6, 16)


def test_returns_none_when_the_quote_is_absent() -> None:
    blocks = [
        AnchorBlock(ordinal=0, content_hash="h0", text="one two three"),
        AnchorBlock(ordinal=1, content_hash="h1", text="four five six"),
    ]

    assert resolve(blocks, quote="nothing here") is None


def test_empty_quote_resolves_to_none() -> None:
    blocks = [AnchorBlock(ordinal=0, content_hash="h0", text="anything")]

    assert resolve(blocks, quote="   ") is None


def test_multi_block_selection_binds_to_the_first_block() -> None:
    # A selection spanning block 0 into block 1: no single block holds the whole
    # quote, so it binds to the first block and runs to that block's end (spec edge).
    blocks = [
        AnchorBlock(ordinal=0, content_hash="h0", text="Alpha beta gamma"),
        AnchorBlock(ordinal=1, content_hash="h1", text="delta epsilon"),
    ]

    binding = resolve(blocks, quote="beta gamma delta")

    assert binding is not None
    assert binding.block_ordinal == 0
    assert binding.block_hash == "h0"
    # Starts at "beta" (index 6) and runs to the end of the normalized block (16).
    assert (binding.start_offset, binding.end_offset) == (6, 16)


def test_prefix_suffix_disambiguate_a_repeated_quote() -> None:
    # "the cat" occurs twice; the context picks the second occurrence.
    blocks = [
        AnchorBlock(ordinal=0, content_hash="h0", text="The cat sat. The cat ran.")
    ]

    binding = resolve(blocks, quote="the cat", prefix="sat.", suffix="ran")

    assert binding is not None
    # Second occurrence begins at index 13 in "the cat sat. the cat ran.".
    assert binding.start_offset == 13


def test_repeated_quote_without_context_binds_the_first_occurrence() -> None:
    blocks = [
        AnchorBlock(ordinal=0, content_hash="h0", text="the cat sat. the cat ran.")
    ]

    binding = resolve(blocks, quote="the cat")

    assert binding is not None
    assert binding.start_offset == 0


def test_tolerates_a_null_block_hash() -> None:
    # A pre-0010 block was never hashed; it still binds, carrying hash None.
    blocks = [AnchorBlock(ordinal=5, content_hash=None, text="unhashed legacy block")]

    binding = resolve(blocks, quote="legacy block")

    assert binding is not None
    assert binding.block_ordinal == 5
    assert binding.block_hash is None
    assert (binding.start_offset, binding.end_offset) == (9, 21)
