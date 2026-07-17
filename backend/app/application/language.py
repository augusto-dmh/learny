"""Stopword-based document language detection (pure; ADR-0025).

PDFs reach the corpus with no declared language (EPUBs carry one in their OPF
metadata), which leaves them on the ``simple`` full-text-search configuration and
outside any localized normalization. This module closes that gap with a small,
dependency-free detector: score a bounded text sample against per-language
stopword tables and return the winning primary subtag only when the evidence is
decisive — otherwise ``None``, which downstream code treats exactly like today.

Like the normalization pass, this is deliberately pure and table-driven: no I/O,
no settings; adding a language is adding a stopword row. Only languages the FTS
layer understands (``app.application.text_search``) are worth adding here.
"""

from __future__ import annotations

import html
import re

from app.domain.entities import ParsedBook

# Distinctive high-frequency function words per language. Words shared between
# the two languages (e.g. "a", "o" appear in English text too rarely vs PT) are
# chosen to minimize cross-matches; accented forms make PT unambiguous.
_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        """the and of to in that it is was for on with as his they at be this
        have from or by not but what all were when we there can an your which
        their said if will each about how up out them then she many some would
        into has more her two like him see time could no make than been its now
        my made over did down only way find use may water long little very after
        words called just where most know""".split()
    ),
    "pt": frozenset(
        """de que e do da em um para com não uma os no se na por mais as dos
        como mas foi ao ele das tem à seu sua ou ser quando muito há nos já
        está eu também só pelo pela até isso ela entre era depois sem mesmo aos
        ter seus quem nas me esse eles estão você tinha foram essa num nem suas
        meu às minha têm numa pelos elas havia seja qual será nós tenho lhe
        deles essas esses pelas este fosse dele""".split()
    ),
}

# Detection gates: below _MIN_TOKENS the sample is too small to trust; the winner
# must beat the runner-up by _MIN_RATIO in stopword hits AND its hits must make
# up at least _MIN_DENSITY of all tokens, else None (ambiguous/foreign text —
# density, not an absolute count, so a shared token like "in" cannot carry a
# foreign language over the bar on volume alone).
_MIN_TOKENS = 200
_MIN_DENSITY = 0.12
_MIN_RATIO = 1.5
_SAMPLE_MAX_WORDS = 5000

_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str) -> str | None:
    """The primary language subtag of ``text``, or ``None`` when unclear.

    Tokenizes to lowercase words, counts hits against each language's stopword
    table, and requires a decisive winner (see the gate constants). Mixed or
    too-short input yields ``None`` rather than a guess.
    """
    tokens = _WORD.findall(text.lower())
    if len(tokens) < _MIN_TOKENS:
        return None
    scores = {
        language: sum(1 for token in tokens if token in stopwords)
        for language, stopwords in _STOPWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (winner, best), (_, second) = ranked[0], ranked[1]
    if best / len(tokens) < _MIN_DENSITY:
        return None
    if second and best / second < _MIN_RATIO:
        return None
    return winner


def sample_text(book: ParsedBook, *, max_words: int = _SAMPLE_MAX_WORDS) -> str:
    """A bounded plain-text sample of the book's opening content.

    Walks sections/blocks in order, strips the block HTML, and stops once
    ``max_words`` words are collected — detection cost stays O(sample), not
    O(book).
    """
    words: list[str] = []
    for section in book.sections:
        for block in section.blocks:
            plain = html.unescape(_TAG.sub(" ", block.html_fragment))
            words.extend(plain.split())
            if len(words) >= max_words:
                return " ".join(words[:max_words])
    return " ".join(words)
