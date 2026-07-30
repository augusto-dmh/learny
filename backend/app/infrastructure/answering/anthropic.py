"""Anthropic Claude generation adapter (ADR-0020, behind a Learny port).

The ``anthropic`` SDK, the model id, and the Citations API request/response shapes
live only in this module — callers depend on ``GenerationPort`` and receive a
Learny-owned ``GeneratedAnswer`` (ADR-0007/0009). Each retrieved chunk becomes one
plain-text citations-enabled ``document`` block, in evidence order; the response's
``document_index`` citations map back through the ordered chunk-id list assembled
at request time — never through ``document_title`` (research §1). Citations are
enabled on every document (all-or-none API rule).

The SDK is imported lazily inside :meth:`_get_client` only, so the module stays
import-light and an injected fake client needs no key or network (mirrors the
OpenAI embedding adapter).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Sequence
from typing import Any, Protocol
from uuid import UUID

from app.domain.entities import (
    MODE_TEACH,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
)
from app.infrastructure.answering.prompts import (
    ANSWER_SYSTEM_PROMPT,
    SENTINEL,
    TEACHING_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# One-hour ephemeral cache breakpoint (research §5): teaching sessions have human
# think-time, so the 5-min TTL would silently re-pay the write between turns. Used
# on the frozen system prompt and the latest history block so the cacheable prefix
# grows with the conversation.
_CACHE_CONTROL = {"type": "ephemeral", "ttl": "1h"}

# Adaptive is the model's own decision about how much to think; ``summarized``
# display is what makes that thinking readable in the response at all — the
# provider default omits the content and returns empty blocks, which is the dead
# air a reader sees while the model reasons. Sent on both request paths so the
# buffered and streamed calls stay one request shape.
_THINKING = {"type": "adaptive", "display": "summarized"}


class _MessagesClient(Protocol):
    """The narrow slice of the Anthropic client this adapter uses (test seam).

    Both the real ``anthropic.Anthropic`` client and the test fake expose
    ``client.messages.create(...)`` returning a message whose ``.content`` is a
    list of blocks (``text`` blocks carry ``.text`` and an optional ``.citations``
    list of objects with ``.document_index``; ``thinking`` blocks carry the
    summarized reasoning and are not part of the answer). The streaming half,
    ``client.messages.stream(...)``, yields ``text`` and ``thinking`` events. Both
    calls accept the ``thinking`` and ``output_config`` request params.
    """

    messages: Any


def _build_documents(
    evidence: Sequence[Evidence],
) -> tuple[list[dict[str, Any]], list[UUID]]:
    """Build one citations-enabled document block per chunk, plus the index map.

    Returns the ordered document blocks (evidence order) and the parallel list of
    ``chunk_id``s — the second list *is* the ``document_index`` → chunk mapping the
    response parser resolves against. ``title`` is the chunk's last section-path
    element (or its anchor when the path is empty); ``context`` is stringified
    ``{chunk_id, anchor}`` metadata passed to the model but never parsed back
    (research §1). Citations are enabled on every document (all-or-none rule).
    """
    documents: list[dict[str, Any]] = []
    chunk_ids: list[UUID] = []
    for item in evidence:
        title = item.section_path[-1] if item.section_path else item.anchor
        context = json.dumps({"chunk_id": str(item.chunk_id), "anchor": item.anchor})
        documents.append(
            {
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": item.snippet,
                },
                "title": title,
                "context": context,
                "citations": {"enabled": True},
            }
        )
        chunk_ids.append(item.chunk_id)
    return documents, chunk_ids


def _parse_message(message: Any, chunk_ids: Sequence[UUID], *, model: str) -> GeneratedAnswer:
    """Parse a Claude message into a ``GeneratedAnswer`` (shared by both modes).

    Concatenates every ``text`` block into the answer text and walks their
    ``citations`` arrays, resolving each ``document_index`` back to a ``chunk_id``
    in first-occurrence order and deduped. An out-of-range index (malformed) is
    skipped — grounding is the second line of defence (AD-027). A whole-reply
    sentinel (after stripping) is the not-found signal → ``found=False`` with empty
    text and citations; an embedded occurrence stays as prose. A ``max_tokens``
    stop reason returns the partial text like any other reply (never raises).
    """
    text_parts: list[str] = []
    cited: list[UUID] = []
    seen: set[UUID] = set()
    for block in message.content:
        if getattr(block, "type", None) != "text":
            continue
        text_parts.append(block.text)
        for citation in getattr(block, "citations", None) or ():
            index = citation.document_index
            if 0 <= index < len(chunk_ids):
                chunk_id = chunk_ids[index]
                if chunk_id not in seen:
                    seen.add(chunk_id)
                    cited.append(chunk_id)
    text = "".join(text_parts)
    if text.strip() == SENTINEL:
        return GeneratedAnswer(text="", cited_chunk_ids=(), model=model, found=False)
    return GeneratedAnswer(text=text, cited_chunk_ids=tuple(cited), model=model, found=True)


def _log_call(message: Any, *, model: str, effort: str, found: bool) -> None:
    """Emit one content-free log line per call — usage counts and outcome only.

    ``effort`` rides along because the token counts on the same line are largely a
    consequence of it: reading latency or spend without knowing which effort bought
    it is how a knob gets tuned blind.
    """
    usage = getattr(message, "usage", None)
    logger.info(
        "anthropic generation model=%s effort=%s input_tokens=%s output_tokens=%s "
        "cache_read_input_tokens=%s stop_reason=%s found=%s",
        model,
        effort,
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(message, "stop_reason", None),
        found,
    )


def _build_history_messages(
    history: Sequence[HistoryTurn],
) -> list[dict[str, Any]]:
    """Render bounded prior turns as alternating user/assistant messages.

    Each :class:`HistoryTurn` becomes a plain-text ``user`` message (the learner's
    ``message``) followed by an ``assistant`` message whose content is a one-element
    text block list (``response_text``). The block-list form on the assistant turn
    is what lets the **latest** history block carry the second ``cache_control``
    breakpoint, so the cached prefix (system + settled history) grows turn over turn
    (research §5). Empty history → no messages and therefore no history breakpoint —
    only the system prompt is cached.
    """
    messages: list[dict[str, Any]] = []
    assistant_blocks: list[dict[str, Any]] = []
    for turn in history:
        messages.append({"role": "user", "content": turn.message})
        block: dict[str, Any] = {"type": "text", "text": turn.response_text}
        messages.append({"role": "assistant", "content": [block]})
        assistant_blocks.append(block)
    if assistant_blocks:
        assistant_blocks[-1]["cache_control"] = _CACHE_CONTROL
    return messages


class AnthropicAdapterBase:
    """Shared construction and lazy client seam for the Anthropic adapters.

    Constructed with the API key, model id, ``max_tokens``, and the thinking
    ``effort`` the composition root read from settings; the real
    ``anthropic.Anthropic`` client is built lazily on first use (so the SDK import
    stays inside this module and an injected fake needs no key/network, mirroring
    the OpenAI embedding adapter). Subclasses add the port-specific ``generate``.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        effort: str = "medium",
        client: _MessagesClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._client = client

    @property
    def model(self) -> str:
        """Stable model identity, readable without a ``generate`` call (QA-04)."""
        return self._model

    def _get_client(self) -> _MessagesClient:
        """Return the injected client, or lazily build ``anthropic.Anthropic``."""
        if self._client is None:
            import anthropic  # local import — the sole SDK reference (ADR-0007/0009)

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _run_stream(
        self,
        *,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        chunk_ids: Sequence[UUID],
    ) -> Iterator[AnswerStreamEvent]:
        """Stream generation events, closing the SDK stream on early cancellation.

        Opens ``messages.stream(...)`` (the SDK context manager), mapping each
        text-delta event to an :class:`~app.domain.entities.AnswerTextDelta`; once
        the stream is exhausted, ``get_final_message()`` is parsed with the **same**
        parser as the buffered path into the authoritative
        :class:`~app.domain.entities.AnswerCompleted`. The ``with`` block guarantees
        the SDK stream is closed when the consumer closes this generator early
        (``GeneratorExit`` unwinds through it), so a client disconnect never leaks a
        provider stream. Shared by both modes — only ``system``/``messages`` differ.
        """
        with self._get_client().messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking=_THINKING,
            output_config={"effort": self._effort},
            system=system,
            messages=messages,
        ) as stream:
            for event in stream:
                if getattr(event, "type", None) == "text":
                    yield AnswerTextDelta(text=event.text)
            final = stream.get_final_message()
        answer = _parse_message(final, chunk_ids, model=self._model)
        _log_call(final, model=self._model, effort=self._effort, found=answer.found)
        yield AnswerCompleted(answer=answer)


class AnthropicGenerationAdapter(AnthropicAdapterBase):
    """``GenerationPort`` implementation over Claude's Citations API (AD-032).

    One adapter for both modes, dispatching **only on the explicit ``mode``** —
    never on whether a target section path was supplied, which a scoped answer
    conversation carries too (AD-194). The document builder, response parser, and
    sentinel logic are shared; the request differs by mode in exactly two places,
    the system prompt and the final user turn:

    - ``answer``: the frozen ``ANSWER_SYSTEM_PROMPT`` with no cache breakpoint, and
      the question as the final user text. With no history that is the single-shot
      ask it has always been.
    - ``teach``: the frozen ``TEACHING_SYSTEM_PROMPT`` carrying a 1-hour
      ``cache_control`` breakpoint, and a final user turn naming the target section
      ahead of the learner's message.

    Either way prior turns render as alternating user/assistant messages with a
    second breakpoint on the latest history block, so the cacheable prefix (system +
    settled history) is byte-stable across a session while every volatile input for
    this turn — the retrieved evidence documents, the target section, and the new
    message — sits strictly *after* the prefix (research §5). The buffered path
    calls ``messages.create`` (``max_tokens`` is far below the SDK's non-streaming
    guard) and carries the same thinking/effort config as the streamed one, with no
    sampling params; the client is built lazily by the shared base so an injected
    fake needs no key/network.
    """

    def _build_request(
        self,
        *,
        message: str,
        mode: str,
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
        target_section_path: tuple[str, ...] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[UUID]]:
        """Assemble the system prompt, the message list, and the chunk map.

        Shared by the buffered and streaming paths so both send the byte-identical
        request, and by both modes so only the two mode-specific pieces differ. The
        teach turn's section header is built from the target the caller resolved;
        the answer turn sends the message alone, whatever target the conversation
        happens to be scoped to.
        """
        documents, chunk_ids = _build_documents(evidence)
        messages = _build_history_messages(history)
        if mode == MODE_TEACH:
            section = " > ".join(target_section_path or ())
            turn_text = f"I am currently studying this section: {section}.\n\n{message}"
            system = [
                {
                    "type": "text",
                    "text": TEACHING_SYSTEM_PROMPT,
                    "cache_control": _CACHE_CONTROL,
                }
            ]
        else:
            turn_text = message
            system = [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
        messages.append(
            {
                "role": "user",
                "content": [*documents, {"type": "text", "text": turn_text}],
            }
        )
        return system, messages, chunk_ids

    def generate(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
    ) -> GeneratedAnswer:
        """Generate a cited response grounded in ``evidence`` (single-shot call)."""
        system, messages, chunk_ids = self._build_request(
            message=message,
            mode=mode,
            history=history,
            evidence=evidence,
            target_section_path=target_section_path,
        )
        response = self._get_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking=_THINKING,
            output_config={"effort": self._effort},
            system=system,
            messages=messages,
        )
        answer = _parse_message(response, chunk_ids, model=self._model)
        _log_call(response, model=self._model, effort=self._effort, found=answer.found)
        return answer

    def generate_stream(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        """Stream a cited response: text deltas, then the authoritative completed event."""
        system, messages, chunk_ids = self._build_request(
            message=message,
            mode=mode,
            history=history,
            evidence=evidence,
            target_section_path=target_section_path,
        )
        return self._run_stream(system=system, messages=messages, chunk_ids=chunk_ids)
