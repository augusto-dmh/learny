"""Tier-2 retrieval eval — hand-labeled ``(query → expected_anchor)`` pairs (EMB-20).

Reviewable code, not derived output (mirrors ``golden_expected``): each pair is
authored by hand and keyed on a stable ``anchor``, never a per-run chunk id. The
target of every query is one chapter of ``golden_corpus.golden_book()`` whose prose
vocabularies are pairwise disjoint (tides / volcanoes / printing), so a query built
from a chapter's own discriminating tokens should retrieve that chapter at rank 1
under both the deterministic-hashing semantic arm and the language-aware lexical arm.

The pairs feed the recall@k / MRR regression gate in
``test_eval_retrieval_metrics``; keep them lexically anchored to their target
chapter (no token borrowed from another chapter's prose) so the gate measures
retrieval quality rather than query ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.golden_corpus import CH1_ANCHOR, CH2_ANCHOR, CH3_ANCHOR


@dataclass(frozen=True)
class LabeledPair:
    """One labeled recall case: a query and the chapter anchor it should retrieve."""

    query: str
    expected_anchor: str


# --- Chapter 1 — "The Rhythm of Tides" (ch1.xhtml) -------------------------------
# Discriminating tokens drawn only from CH1 prose/title: ocean, tides, rise, fall,
# moon, gravity, pulls, seawater, planet, sun, align, spring, swell, highest, water,
# coastline, rhythm. No volcano/printing token appears here.
_CH1_PAIRS = (
    LabeledPair("How does the moon's gravity pull seawater into tides?", CH1_ANCHOR),
    LabeledPair("Why do ocean tides rise and fall across the planet?", CH1_ANCHOR),
    LabeledPair("What causes spring tides when the moon and sun align?", CH1_ANCHOR),
    LabeledPair("The rhythm of tides swelling along the coastline", CH1_ANCHOR),
    LabeledPair("Gravity pulling seawater over the whole planet", CH1_ANCHOR),
    LabeledPair("When the sun and moon align their gravity into spring tides", CH1_ANCHOR),
    LabeledPair("Spring tides swell to the highest water on the coastline", CH1_ANCHOR),
    LabeledPair("Ocean tides driven by the moon's gravitational pull on seawater", CH1_ANCHOR),
    LabeledPair("Seawater pulled across the planet as tides rise and fall", CH1_ANCHOR),
    LabeledPair("The moon and sun aligning to swell the highest water", CH1_ANCHOR),
    LabeledPair("Rising and falling tides along every coastline", CH1_ANCHOR),
    LabeledPair("Why seawater swells into spring tides", CH1_ANCHOR),
    LabeledPair("The rhythm of ocean tides and the moon's gravity", CH1_ANCHOR),
    LabeledPair("Tides rise and fall because the moon pulls seawater", CH1_ANCHOR),
)

# --- Chapter 2 — "How Volcanoes Erupt" (ch2.xhtml) -------------------------------
# Discriminating tokens drawn only from CH2 prose/title: volcano, erupts, molten,
# magma, escapes, upward, vent, crust, basalt, lava, flows, spread, ash, billows,
# crater, eruption. No tide/printing token appears here.
_CH2_PAIRS = (
    LabeledPair("How does a volcano erupt when magma escapes upward?", CH2_ANCHOR),
    LabeledPair("Molten magma rising through a vent in the crust", CH2_ANCHOR),
    LabeledPair("Why does basalt lava flow from an erupting volcano?", CH2_ANCHOR),
    LabeledPair("Basalt lava spreading from the crater", CH2_ANCHOR),
    LabeledPair("Ash billowing from the crater during an eruption", CH2_ANCHOR),
    LabeledPair("How volcanoes erupt through the crust", CH2_ANCHOR),
    LabeledPair("Magma escaping upward through a vent to erupt", CH2_ANCHOR),
    LabeledPair("A volcanic eruption spreading basalt lava flows", CH2_ANCHOR),
    LabeledPair("What makes ash billow during a volcanic eruption?", CH2_ANCHOR),
    LabeledPair("Molten magma escaping upward to erupt from the vent", CH2_ANCHOR),
    LabeledPair("The crater releasing lava flows and billowing ash", CH2_ANCHOR),
    LabeledPair("Magma pushing up through the crust to erupt as lava", CH2_ANCHOR),
    LabeledPair("Basalt lava flows and billowing ash from a volcano", CH2_ANCHOR),
    LabeledPair("When molten magma escapes through a vent in the crust", CH2_ANCHOR),
)

# --- Chapter 3 — "The Printing Press" (ch3.xhtml) --------------------------------
# Discriminating tokens drawn only from CH3 prose/title: printing, press, workshop,
# reproduce, page, movable, metal, type, inked, letters, pressed, paper, pamphlets,
# scribe, copy (and "books"). No tide/volcano token appears here.
_CH3_PAIRS = (
    LabeledPair("How did the printing press reproduce a page?", CH3_ANCHOR),
    LabeledPair("Movable metal type on the printing press", CH3_ANCHOR),
    LabeledPair("Inked letters pressed onto paper", CH3_ANCHOR),
    LabeledPair("A workshop reproducing a page from movable type", CH3_ANCHOR),
    LabeledPair("Pamphlets printed faster than a scribe could copy them", CH3_ANCHOR),
    LabeledPair("How movable metal type reproduced a printed page", CH3_ANCHOR),
    LabeledPair("The printing press and its movable metal type", CH3_ANCHOR),
    LabeledPair("Inked letters carried onto paper as pamphlets", CH3_ANCHOR),
    LabeledPair("A scribe copying pages against the printing press", CH3_ANCHOR),
    LabeledPair("Reproducing books with a workshop's movable metal type", CH3_ANCHOR),
    LabeledPair("Pressed letters printing pamphlets and books", CH3_ANCHOR),
    LabeledPair("The workshop that pressed pages from movable type", CH3_ANCHOR),
    LabeledPair("Paper carrying inked letters faster than any scribe", CH3_ANCHOR),
    LabeledPair("Movable type letting a workshop reproduce a page", CH3_ANCHOR),
)

# 42 hand-labeled pairs — within the reviewable 30–60 band (EMB-20), ~14 distinct
# phrasings per chapter so the gate averages over varied queries, not one lucky hit.
LABELED_PAIRS: tuple[LabeledPair, ...] = _CH1_PAIRS + _CH2_PAIRS + _CH3_PAIRS

__all__ = ["LABELED_PAIRS", "LabeledPair"]
