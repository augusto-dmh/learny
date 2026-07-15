"""B1 gate (unit) — language → regconfig resolution (EMB-10).

Pure function, no DB. Covers the allowlist, primary-subtag extraction with mixed
separators/case, full-config passthrough, and the ``simple`` fallback.
"""

from __future__ import annotations

import pytest

from app.application.text_search import resolve_text_search_config


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "english"),
        ("pt", "portuguese"),
        ("es", "spanish"),
        ("fr", "french"),
        ("de", "german"),
    ],
)
def test_primary_subtag_maps_to_config(language: str, expected: str) -> None:
    assert resolve_text_search_config(language) == expected


@pytest.mark.parametrize("language", ["pt-BR", "pt_br", "PT-br", "  pt  ", "PT"])
def test_case_and_separator_insensitive(language: str) -> None:
    # The primary subtag ``pt`` resolves regardless of region, case, separator,
    # or surrounding whitespace (EMB-10).
    assert resolve_text_search_config(language) == "portuguese"


def test_full_config_name_passes_through() -> None:
    # A value that is already a resolved regconfig round-trips unchanged, so
    # re-resolving a stored ``search_config`` is idempotent.
    assert resolve_text_search_config("portuguese") == "portuguese"
    assert resolve_text_search_config("PORTUGUESE") == "portuguese"
    assert resolve_text_search_config("simple") == "simple"


@pytest.mark.parametrize("language", [None, "", "   ", "xx", "klingon", "zz-ZZ"])
def test_unknown_or_blank_falls_back_to_simple(language: str | None) -> None:
    assert resolve_text_search_config(language) == "simple"
