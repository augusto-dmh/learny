"""Frozen generation prompts and the not-found sentinel (design §2, ADR-0020).

The system prompts are **byte-stable constants** — no per-request or per-session
interpolation (no ids, timestamps, or evidence) — so they are safe to reuse as a
cacheable prompt prefix (the teaching adapter puts a ``cache_control`` breakpoint
on this exact string, ADR-0020 / research §5). Per-turn volatile content (evidence
documents, the question, the target section, the learner message) always lives in
the message turns, never here.

The sentinel is the deterministic not-found signal: because the Citations API and
structured outputs are mutually exclusive (400 error, research §2), a frozen
prompt instructing the model to reply with exactly ``SENTINEL`` is how relevance
is judged — the adapter maps a whole-reply sentinel to ``found=False`` (F5).
"""

from __future__ import annotations

# Re-exported from the domain so the prompt text and the streaming hold-back guard
# (application layer) share one source of truth. Exact string the model must
# return, alone, when the documents cannot answer the question. Whole-reply match
# only — the adapter never treats an embedded occurrence as not-found (guards
# against sentinel leakage in prose).
from app.domain.entities import SENTINEL

__all__ = ["ANSWER_SYSTEM_PROMPT", "SENTINEL", "TEACHING_SYSTEM_PROMPT"]

ANSWER_SYSTEM_PROMPT = (
    "You are Learny's book-grounded answering assistant. Answer the reader's "
    "question using only the information contained in the provided documents. "
    "Cite the specific passages you rely on. Do not use outside knowledge and do "
    "not speculate beyond what the documents state. If the provided documents do "
    "not contain the information needed to answer the question, reply with "
    f"exactly {SENTINEL} and nothing else."
)

TEACHING_SYSTEM_PROMPT = (
    "You are Learny's patient book tutor. Teach the learner about the passage "
    "they are studying using only the information contained in the provided "
    "documents, building naturally on the conversation so far. Cite the specific "
    "passages you rely on. Do not use outside knowledge and do not speculate "
    "beyond what the documents state. If the provided documents do not support a "
    f"grounded response to the learner's message, reply with exactly {SENTINEL} "
    "and nothing else."
)
