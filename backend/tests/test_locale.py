"""Interface-language rules (pure): negotiation and effective locale.

``NEGOTIATION_VECTORS`` is the shared vector table: the frontend's
``negotiateLocale`` (``frontend/tests/i18n-config.test.ts``) asserts the same
inputs against the same outputs, so the two implementations cannot drift.
"""

from __future__ import annotations

import pytest

from app.domain.locale import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    effective_locale,
    negotiate_locale,
    response_language_for,
)

NEGOTIATION_VECTORS: list[tuple[str | None, str]] = [
    ("pt", "pt-BR"),
    ("pt-BR", "pt-BR"),
    ("pt-PT", "pt-BR"),
    ("pt;q=0.9,en;q=0.8", "pt-BR"),
    ("en,pt", "en"),
    ("en;q=0.5,pt;q=0.9", "pt-BR"),
    ("pt-BR,pt;q=0.9,en;q=0.8", "pt-BR"),
    ("en-US,en;q=0.9", "en"),
    ("fr,pt;q=0.5", "pt-BR"),
    # Fall-back to en: absent, malformed, unsupported-only, not acceptable.
    (None, "en"),
    ("", "en"),
    (";;;", "en"),
    ("pt;q=abc", "en"),
    ("fr,de", "en"),
    ("*", "en"),
    ("pt;q=0", "en"),
]


def test_the_supported_locales_are_exactly_en_and_pt_br() -> None:
    assert SUPPORTED_LOCALES == ("en", "pt-BR")
    assert DEFAULT_LOCALE == "en"


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
