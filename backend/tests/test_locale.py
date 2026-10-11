"""Interface-language rules (pure): negotiation and effective locale.

``NEGOTIATION_VECTORS`` comes from ``locale_negotiation_vectors.json``, which the
frontend's ``negotiateLocale`` test (``frontend/tests/i18n-config.test.ts``) also
reads, so the two implementations are held to the same inputs and outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.locale import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    effective_locale,
    negotiate_locale,
    response_language_for,
)

# The shared vector table: the frontend's ``negotiateLocale`` test reads the same
# file, so the two implementations are held to one list rather than two copies.
_VECTORS_FILE = Path(__file__).with_name("locale_negotiation_vectors.json")
NEGOTIATION_VECTORS: list[tuple[str | None, str]] = [
    (header, expected) for header, expected in json.loads(_VECTORS_FILE.read_text())["vectors"]
]


def test_the_supported_locales_are_exactly_en_and_pt_br() -> None:
    assert SUPPORTED_LOCALES == ("en", "pt-BR")
    assert DEFAULT_LOCALE == "en"


def test_the_shared_vector_table_is_loaded() -> None:
    """An empty or unreadable table would make the parametrized test vacuous."""
    assert len(NEGOTIATION_VECTORS) > 20
    assert {expected for _, expected in NEGOTIATION_VECTORS} == set(SUPPORTED_LOCALES)


@pytest.mark.parametrize(("header", "expected"), NEGOTIATION_VECTORS)
def test_negotiation_vectors(header: str | None, expected: str) -> None:
    assert negotiate_locale(header) == expected


@pytest.mark.parametrize(
    ("stored", "header", "expected"),
    [
        ("en", "pt-BR", "en"),  # a stored choice beats the header
        ("pt-BR", "en-US", "pt-BR"),
        (None, "pt-BR", "pt-BR"),  # unset negotiates
        (None, None, "en"),
        ("fr", "pt-BR", "pt-BR"),  # an unsupported stored value reads as unset
        ("PT-BR", "en", "en"),  # case-exact: a miscased value is unsupported
        ("", "pt", "pt-BR"),
    ],
)
def test_effective_locale_precedence(stored: str | None, header: str | None, expected: str) -> None:
    assert effective_locale(stored, header) == expected


def test_response_language_is_requested_only_for_non_english_locales() -> None:
    assert response_language_for("en") is None
    assert response_language_for("pt-BR") == "pt-BR"
    assert response_language_for("fr") is None
