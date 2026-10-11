"""Interface-language rules shared by the preference API and answer generation.

Two locales exist: ``en`` and ``pt-BR`` (BCP 47, case-exact). The set lives here,
in code, rather than in a database constraint so a third locale is a catalog
change and not a migration; a stored value outside the set reads as unset.

``negotiate_locale`` and the frontend's ``negotiateLocale`` implement the same
rule over the same vector table (``backend/tests/locale_negotiation_vectors.json``,
read by both test suites): order the header's tags by q-value, then by position;
the first tag whose primary subtag is ``pt`` or ``en`` decides, and any ``pt`` or
``pt-*`` maps to ``pt-BR``. A q-value must match the RFC 9110 ``qvalue`` grammar
(``0`` to ``1``, at most three decimals); anything else makes its tag malformed.

``effective_locale`` and ``response_language_for`` are staged for the
answer-language work (the generation port's response-language argument); until
that lands, the preference API is their only neighbour and they have no caller.
"""

from __future__ import annotations

import re

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "pt-BR")
DEFAULT_LOCALE = "en"

# The locale that needs no instruction: answers are requested in English by
# default, so prompts, replay snapshots and cache prefixes stay byte-identical.
_UNINSTRUCTED_LOCALE = "en"

_PRIMARY_SUBTAG_TO_LOCALE = {"en": "en", "pt": "pt-BR"}

# RFC 9110 qvalue: "0" or "1" with up to three decimals, never above 1.
_QVALUE = re.compile(r"0(\.\d{0,3})?|1(\.0{0,3})?")


def is_supported_locale(value: object) -> bool:
    """True only for the exact supported spellings."""
    return isinstance(value, str) and value in SUPPORTED_LOCALES


def negotiate_locale(accept_language: str | None) -> str:
    """Pick a supported locale from an ``Accept-Language`` header; ``en`` otherwise.

    Absent, malformed or unsupported-only headers fall back to ``en``. A tag with
    ``q=0`` is "not acceptable" and a tag whose q-value does not parse is skipped.
    """
    if not accept_language:
        return DEFAULT_LOCALE
    ranked: list[tuple[float, int, str]] = []
    for position, part in enumerate(accept_language.split(",")):
        tag, *params = (piece.strip() for piece in part.split(";"))
        if not tag or tag == "*":
            continue
        quality = _quality(params)
        if quality is None or quality <= 0:
            continue
        ranked.append((quality, position, tag))
    for _quality_value, _position, tag in sorted(ranked, key=lambda item: (-item[0], item[1])):
        locale = _PRIMARY_SUBTAG_TO_LOCALE.get(tag.split("-", 1)[0].lower())
        if locale is not None:
            return locale
    return DEFAULT_LOCALE


def _quality(params: list[str]) -> float | None:
    """The q-value among a tag's parameters (1.0 when absent); None when malformed."""
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() == "q":
            value = value.strip()
            return float(value) if _QVALUE.fullmatch(value) else None
    return 1.0


def effective_locale(stored: str | None, accept_language: str | None) -> str:
    """The learner's locale: a supported stored choice, else the negotiated one."""
    if stored is not None and is_supported_locale(stored):
        return stored
    return negotiate_locale(accept_language)


def response_language_for(locale: str) -> str | None:
    """The response language to request from a generator, or ``None`` for ``en``."""
    if locale == _UNINSTRUCTED_LOCALE or not is_supported_locale(locale):
        return None
    return locale
