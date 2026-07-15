"""Language → Postgres text-search regconfig resolution (EMB-10).

A pure function — no I/O, no libraries, no framework imports (ADR-0009). Maps a
``dc:language`` value (as carried on ``corpus_documents.language``) to a built-in
Postgres full-text ``regconfig`` name, so each chunk's lexical arm stems in the
book's own language rather than a hardcoded ``english`` (QA finding F8).

Resolution is case- and separator-insensitive: the primary subtag of a BCP-47-ish
tag (``pt-BR``, ``pt_br``, ``PORTUGUESE``) is taken and looked up in an allowlist
of Postgres' bundled snowball configs. An input that is already a full config name
passes through. Anything unknown, blank, or ``None`` falls back to ``simple`` (no
stemming, no stop words) — a safe default that never fails on an unrecognized
language.
"""

from __future__ import annotations

# Primary-subtag → Postgres regconfig, restricted to configs shipped in a stock
# Postgres (the snowball stemmers). Extend deliberately; an absent language is
# ``simple``, not a guess.
_LANGUAGE_TO_CONFIG: dict[str, str] = {
    "en": "english",
    "pt": "portuguese",
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "it": "italian",
    "nl": "dutch",
    "ru": "russian",
    "sv": "swedish",
    "da": "danish",
    "no": "norwegian",
    "fi": "finnish",
    "hu": "hungarian",
    "ro": "romanian",
    "tr": "turkish",
}

# The regconfig values themselves, so a caller that already stored a resolved
# config name (e.g. re-resolving ``'portuguese'``) gets it back unchanged.
_ALLOWED_CONFIGS: frozenset[str] = frozenset(_LANGUAGE_TO_CONFIG.values())

_FALLBACK_CONFIG = "simple"


def resolve_text_search_config(language: str | None) -> str:
    """Return the Postgres text-search regconfig for a document ``language``.

    Lowercases and trims the input, splits on ``-``/``_`` to take the primary
    subtag, and looks it up in the allowlist. A value that is already an allowed
    config name is passed through. ``None``, blank, or an unknown language →
    ``simple`` (RET/EMB-10). Pure and total — never raises.
    """
    if language is None:
        return _FALLBACK_CONFIG
    normalized = language.strip().lower()
    if not normalized:
        return _FALLBACK_CONFIG
    if normalized in _ALLOWED_CONFIGS:
        return normalized
    primary = normalized.replace("_", "-").split("-", 1)[0]
    return _LANGUAGE_TO_CONFIG.get(primary, _FALLBACK_CONFIG)
