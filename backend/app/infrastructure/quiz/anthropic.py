"""Anthropic Message Batches quiz adapter (QUIZ-05 batched path, behind the Learny port).

The ``anthropic`` SDK, the model id, and the batch/structured-output request shapes live
only in this module — callers depend on ``QuizGenerationPort`` and receive Learny-owned
candidates (ADR-0007/0009). Generation is asynchronous: ``begin_deck`` submits **one**
Message Batches request per eligible section (each a single structured-output message
whose ``source_chunk_id`` enum is constrained to that section's chunk ids), and returns a
handle carrying the batch id plus the per-section chunk-id map; ``collect_deck`` polls the
batch and returns ``None`` while it is still processing, mapping each ended result back to
its section by ``custom_id`` once it ends (per-request failures become section errors, a
partial-success deck). The QC pipeline downstream re-verifies every candidate, so the
adapter parses leniently and never trusts the model's grounding on its own.

SDK note (verified at install, ``anthropic==0.116``): ``messages.batches.create`` accepts
``params`` as a full ``MessageCreateParams`` including ``output_config``, so structured
outputs are legal inside a batch — no prompt-JSON fallback is needed. ``batches.retrieve``
exposes ``processing_status`` (``in_progress``/``canceling``/``ended``) and
``batches.results`` yields ``(custom_id, result)`` where ``result.type`` is
``succeeded``/``errored``/``canceled``/``expired``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.domain.entities import (
    QuizCandidate,
    QuizDeckHandle,
    QuizDeckResult,
    QuizItemType,
    QuizSection,
)
from app.infrastructure.answering.anthropic import AnthropicAdapterBase

# Wall-clock bound for the one foreground generation call (card suggestions). The deck
# path is batched and asynchronous, so it is deliberately unaffected. Chosen well under
# a reader's patience: past this the student has already given up, and holding the
# threadpool slot only makes the next request worse.
_SUGGEST_TIMEOUT_S = 30.0


def _custom_id(index: int, anchor: str) -> str:
    """Return a batch-legal, section-unique custom id derived from the anchor.

    Batch custom ids must match ``[a-zA-Z0-9_-]{1,64}``, which raw anchors
    (``ch01.xhtml#sec``) violate; the positional prefix guarantees uniqueness even when
    two sections share an anchor, and the anchor hash ties the id back to the section.
    """
    digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:12]
    return f"section-{index}-{digest}"


def _items_schema(chunk_ids: Sequence[str]) -> dict[str, Any]:
    """Per-section json_schema: an ``items`` array constrained to this section's chunks."""
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_type": {
                            "type": "string",
                            "enum": [QuizItemType.FREE_RECALL, QuizItemType.CLOZE],
                        },
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                        # Constrain the citation to the section's own chunks (QUIZ-05).
                        "source_chunk_id": {"type": "string", "enum": list(chunk_ids)},
                        "anchor_quote": {"type": "string"},
                    },
                    "required": [
                        "item_type",
                        "question",
                        "answer",
                        "source_chunk_id",
                        "anchor_quote",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def _section_prompt(section: QuizSection) -> str:
    """Render the section's text (chunks labeled by id) plus the item-writing instruction."""
    path = " > ".join(section.section_path)
    chunks_text = "\n\n".join(
        f"[chunk {chunk_id}]\n{text}" for chunk_id, text in section.chunks
    )
    return (
        "You are writing active-recall study items for one section of a book.\n"
        f"Section: {path}\n\n"
        f"Source text (each chunk is labeled with its id):\n{chunks_text}\n\n"
        "Write 3 to 6 items grounded strictly in the source text above. Each item must set "
        "source_chunk_id to the id of the chunk it is drawn from and anchor_quote to a "
        "sentence copied verbatim from that chunk. Use item_type 'free_recall' for a "
        "question/answer pair, or 'cloze' for a fill-in-the-blank where the question is a "
        "sentence from the chunk with the key term replaced by ____ and answer is that term."
    )


def _quote_prompt(section: QuizSection, quote: str, limit: int) -> str:
    """Render the section's text plus the instruction to write items for one quote."""
    path = " > ".join(section.section_path)
    chunks_text = "\n\n".join(
        f"[chunk {chunk_id}]\n{text}" for chunk_id, text in section.chunks
    )
    return (
        "You are writing active-recall study items for one passage a student "
        "highlighted while reading.\n"
        f"Section: {path}\n\n"
        f"Section text (each chunk is labeled with its id):\n{chunks_text}\n\n"
        f"Highlighted passage:\n{quote}\n\n"
        f"Write at most {limit} items about the highlighted passage only, grounded "
        "strictly in the section text above. Each item must set source_chunk_id to the "
        "id of the chunk the highlighted passage appears in and anchor_quote to a "
        "sentence copied verbatim from that chunk. Use item_type 'free_recall' for a "
        "question/answer pair, or 'cloze' for a fill-in-the-blank where the question is "
        "a sentence from the chunk with the key term replaced by ____ and answer is "
        "that term."
    )


def _first_text(message: Any) -> str:
    """Return the first ``text`` block's text from a Claude message."""
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("batch response contained no text block")


def _parse_items(message: Any) -> list[QuizCandidate]:
    """Parse a section's structured-output message into candidates (QC re-verifies)."""
    data = json.loads(_first_text(message))
    return [
        QuizCandidate(
            item_type=item["item_type"],
            question=item["question"],
            answer=item["answer"],
            source_chunk_id=UUID(item["source_chunk_id"]),
            anchor_quote=item["anchor_quote"],
        )
        for item in data["items"]
    ]


def _note_items_schema() -> dict[str, Any]:
    """json_schema for note candidates: no ``source_chunk_id`` (a note is not chunked)."""
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_type": {
                            "type": "string",
                            "enum": [QuizItemType.FREE_RECALL, QuizItemType.CLOZE],
                        },
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                        "anchor_quote": {"type": "string"},
                    },
                    "required": ["item_type", "question", "answer", "anchor_quote"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def _note_prompt(note_body: str, context: str, limit: int) -> str:
    """Render the note body (+ book context when anchored) plus the item-writing task."""
    context_block = (
        f"\n\nBook context this note refers to:\n{context}" if context.strip() else ""
    )
    return (
        "You are writing active-recall study items from a reader's own note.\n"
        f"Note:\n{note_body}{context_block}\n\n"
        f"Write at most {limit} items grounded strictly in the note text above. Set "
        "anchor_quote to a sentence copied verbatim from the note. Use item_type "
        "'free_recall' for a question/answer pair, or 'cloze' for a fill-in-the-blank "
        "where the question is a sentence from the note with the key term replaced by "
        "____ and answer is that term."
    )


def _parse_note_items(message: Any) -> list[QuizCandidate]:
    """Parse a note's structured-output message into candidates (QC re-verifies)."""
    data = json.loads(_first_text(message))
    return [
        QuizCandidate(
            item_type=item["item_type"],
            question=item["question"],
            answer=item["answer"],
            anchor_quote=item["anchor_quote"],
        )
        for item in data["items"]
    ]


class AnthropicQuizAdapter(AnthropicAdapterBase):
    """``QuizGenerationPort`` over Claude's Message Batches + structured outputs.

    Reuses the shared lazy-client base (``model`` identity, injected fake client) so tests
    stay offline. One batch request per section keeps ``source_chunk_id`` constrained to
    that section's chunks; the handle carries the batch id and the section map for polling.
    """

    def begin_deck(self, sections: Sequence[QuizSection]) -> QuizDeckHandle:
        """Submit one structured-output batch request per section; return a poll handle.

        With no sections there is nothing to submit, so no batch is created and the handle
        carries no batch id (``collect_deck`` then returns an empty result immediately).
        """
        requests: list[dict[str, Any]] = []
        section_meta: dict[str, dict[str, Any]] = {}
        for index, section in enumerate(sections):
            custom_id = _custom_id(index, section.anchor)
            chunk_ids = [str(chunk_id) for chunk_id, _ in section.chunks]
            requests.append(
                {
                    "custom_id": custom_id,
                    "params": {
                        "model": self._model,
                        "max_tokens": self._max_tokens,
                        "messages": [
                            {"role": "user", "content": _section_prompt(section)}
                        ],
                        "output_config": {
                            "format": {
                                "type": "json_schema",
                                "schema": _items_schema(chunk_ids),
                            }
                        },
                    },
                }
            )
            section_meta[custom_id] = {"chunk_ids": chunk_ids}

        if not requests:
            return QuizDeckHandle(provider="anthropic", batch_id=None, payload={"sections": {}})

        batch = self._get_client().messages.batches.create(requests=requests)
        return QuizDeckHandle(
            provider="anthropic",
            batch_id=batch.id,
            payload={"sections": section_meta},
        )

    def suggest_cards(
        self, section: QuizSection, quote: str, limit: int
    ) -> list[QuizCandidate]:
        """Issue one Messages call for ``quote`` and return at most ``limit`` candidates.

        Synchronous by design (AD-134) — the student is waiting — but structurally the
        same request as one batch entry: the same ``_items_schema`` with
        ``source_chunk_id`` constrained to this section's chunk ids, so grounding stays
        schema-enforced. Malformed structured output raises ``ValueError`` for the caller
        to surface as a retryable failure; the QC pipeline still re-verifies whatever
        parses.
        """
        if limit <= 0 or not section.chunks:
            return []
        chunk_ids = [str(chunk_id) for chunk_id, _ in section.chunks]
        message = self._get_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": _quote_prompt(section, quote, limit)}],
            output_config={
                "format": {"type": "json_schema", "schema": _items_schema(chunk_ids)}
            },
            # Bounded per call rather than on the shared client, which the streaming
            # answer path also uses and where a long read is legitimate. This one is a
            # student waiting on a popover, and it occupies a threadpool slot while it
            # waits: on the SDK default a hung connection would hold that slot for ten
            # minutes. Rate limiting caps how often this is entered, not how long it
            # stays, so the bound has to live here.
            timeout=_SUGGEST_TIMEOUT_S,
        )
        try:
            candidates = _parse_items(message)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"suggestion response was not usable: {exc}") from exc
        return candidates[:limit]

    def suggest_note_cards(
        self, note_body: str, context: str, limit: int
    ) -> list[QuizCandidate]:
        """Issue one Messages call for a note and return at most ``limit`` candidates.

        Synchronous by design (AD-134) — the reader is waiting — and structurally the
        note→quiz mirror of :meth:`suggest_cards`: the same ``timeout`` bound, but the
        ``_note_items_schema`` drops ``source_chunk_id`` (a note is not chunked) and the
        prompt carries the note's book context only when present. Malformed structured
        output raises ``ValueError`` for the caller to surface as a retryable failure; the
        QC pipeline still re-verifies whatever parses against the note body.
        """
        if limit <= 0 or not note_body.strip():
            return []
        message = self._get_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": _note_prompt(note_body, context, limit)}],
            output_config={
                "format": {"type": "json_schema", "schema": _note_items_schema()}
            },
            timeout=_SUGGEST_TIMEOUT_S,
        )
        try:
            candidates = _parse_note_items(message)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"note suggestion response was not usable: {exc}") from exc
        return candidates[:limit]

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        """Poll the batch; ``None`` while processing, else the mapped result (QUIZ-05)."""
        if handle.batch_id is None:
            return QuizDeckResult(candidates=(), errors=())

        client = self._get_client()
        batch = client.messages.batches.retrieve(handle.batch_id)
        if batch.processing_status != "ended":
            return None

        candidates: list[QuizCandidate] = []
        errors: list[str] = []
        for response in client.messages.batches.results(handle.batch_id):
            result = response.result
            if result.type != "succeeded":
                errors.append(f"{response.custom_id}: {result.type}")
                continue
            try:
                candidates.extend(_parse_items(result.message))
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f"{response.custom_id}: {exc}")
        return QuizDeckResult(candidates=tuple(candidates), errors=tuple(errors))
