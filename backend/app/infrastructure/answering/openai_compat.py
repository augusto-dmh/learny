"""OpenAI-compatible generation adapter (the prompt-cited second kind, ADR-0020).

The ``openai`` SDK, the model id, the ``base_url``, and the chat-completions
request/response shapes live only in this module — callers depend on
``GenerationPort`` and receive a Learny-owned ``GeneratedAnswer`` (ADR-0007/0009).
This kind has no provider-side citation API: the system prompt carries the same
Learny not-found sentinel and instructs prompt-id citations — evidence documents
are numbered ``[1]``, ``[2]``, … in evidence order, and the model marks each claim
with the cited document's ``[^n]``. Marker *n* resolves to ``evidence[n-1]``'s
chunk id in first-occurrence order; an out-of-range marker names no chunk. A
prompt-cited reply gives no honest character offsets, so no span is ever reported
— the grounding intersection (``app.application.grounding``) stays the verifier
(AD-027 backstop), exactly as for the Citations adapter.

Usage maps ``prompt_tokens``/``completion_tokens`` plus the cached-token detail
the host reports into the Learny usage DTO; a response without usage parses to
``None`` → the debit is 0 (ECON-03). Thinking effort cannot be expressed on this
kind: the profile's per-mode values are accepted and deliberately never sent
(ECON-05, declared degradation). SDK/HTTP failures translate to the Learny
taxonomy through the providers package's shared translator (TAX-02), with this
adapter's SDK exception types bound in; anything unrecognized propagates
unchanged so the application's error envelope is exactly as before (TAX-03).

The SDK is imported lazily inside :meth:`_get_client` only, so the module stays
import-light and an injected fake client needs no key or network (mirrors the
OpenAI embedding adapter).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any, NoReturn, Protocol
from uuid import UUID

from app.domain.entities import (
    CITATION_MARKER_RE,
    MODE_TEACH,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    TokenUsage,
)
from app.infrastructure.answering.prompts import SENTINEL
from app.infrastructure.providers.translation import (
    raise_translated as _raise_translated_shared,
)

logger = logging.getLogger(__name__)

# Wall-clock bound for the buffered call (TAX-01, anchored at the generate bound
# the Anthropic adapter already uses): a buffered reply returns nothing until the
# whole answer is written. The streaming path is deliberately unbounded here —
# its frames prove progress as they arrive.
_GENERATE_TIMEOUT_S = 120.0

# The shape every request this adapter builds has: numbered documents cited by
# ``[^n]`` markers, no structured-output format, and no effort parameter. Named
# on the redacted 4xx line so a rejection can be read against the shape that
# earned it (the Anthropic adapter's ``citations`` analog).
_REQUEST_SHAPE = "prompt-cited"

# Frozen system prompt — no per-request or per-session interpolation. It carries
# the cross-provider not-found sentinel (the prompt-level contract, provider
# agnostic) and the ``[^n]``-into-evidence citation convention (ECON-02).
COMPAT_SYSTEM_PROMPT = (
    "You are Learny's book-grounded answering assistant. Answer the reader's "
    "question using only the information contained in the provided documents. "
    "The documents are numbered [1], [2], and so on. Cite the specific passages "
    "you rely on by writing the cited document's number as an inline marker "
    "directly after the claim it supports: [^1], [^2], and so on. Do not use "
    "outside knowledge and do not speculate beyond what the documents state. If "
    "the provided documents do not contain the information needed to answer the "
    f"question, reply with exactly {SENTINEL} and nothing else."
)


class _ChatClient(Protocol):
    """The narrow slice of the OpenAI client this adapter uses (test seam).

    Both the real ``openai.OpenAI`` client and the test fake expose
    ``client.chat.completions.create(...)`` returning a completion whose
    ``.choices[0].message.content`` is the reply text and whose ``.usage``
    carries ``prompt_tokens``/``completion_tokens`` (plus
    ``prompt_tokens_details.cached_tokens`` when the host reports it).
    """

    chat: Any


def _build_user_content(
    *,
    message: str,
    mode: str,
    evidence: Sequence[Evidence],
    target_section_path: tuple[str, ...] | None,
    tutor_phase: str | None,
    hint_level: str | None,
) -> str:
    """Assemble the user turn: the numbered documents, then the learner's input.

    Documents are numbered by evidence order — that number *is* the ``[^n]``
    marker's referent, so the parse needs no per-request state beyond the same
    ordered ``evidence`` sequence. A teach turn opens with the section header
    the tutor envelope carries (mirroring the Anthropic adapter's user-turn
    placement); with no documents the turn is the header and the message alone.
    """
    parts: list[str] = []
    if mode == MODE_TEACH:
        section = " > ".join(target_section_path or ())
        header = [f"I am currently studying this section: {section}."]
        if tutor_phase is not None:
            header.append(f"Phase: {tutor_phase}")
        if hint_level is not None:
            header.append(f"HintLevel: {hint_level}")
        parts.append("\n".join(header))
    parts.extend(f"[{number}]\n{item.snippet}" for number, item in enumerate(evidence, start=1))
    parts.append(message)
    return "\n\n".join(parts)


def _build_messages(
    *,
    message: str,
    mode: str,
    history: Sequence[HistoryTurn],
    evidence: Sequence[Evidence],
    target_section_path: tuple[str, ...] | None,
    tutor_phase: str | None,
    hint_level: str | None,
) -> list[dict[str, str]]:
    """The chat messages: frozen system prompt, bounded history, this turn."""
    messages: list[dict[str, str]] = [{"role": "system", "content": COMPAT_SYSTEM_PROMPT}]
    for turn in history:
        # A stored answer carries the ``[^n]`` marks this adapter parses; they
        # are Learny's, not the model's, and replay them would teach a token the
        # model cannot number correctly — strip at this one choke point.
        messages.append({"role": "user", "content": turn.message})
        messages.append(
            {"role": "assistant", "content": CITATION_MARKER_RE.sub("", turn.response_text)}
        )
    messages.append(
        {
            "role": "user",
            "content": _build_user_content(
                message=message,
                mode=mode,
                evidence=evidence,
                target_section_path=target_section_path,
                tutor_phase=tutor_phase,
                hint_level=hint_level,
            ),
        }
    )
    return messages


def _cached_tokens(usage: Any) -> int | None:
    """The cached-input count a host reports via ``prompt_tokens_details``, else None."""
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return None
    cached = getattr(details, "cached_tokens", None)
    return cached if isinstance(cached, int) else None


def _usage_of(response: Any) -> TokenUsage | None:
    """Map a completion's ``usage`` onto the Learny usage DTO (ECON-03).

    ``prompt_tokens``/``completion_tokens`` are the debit's input and output;
    the cached-input detail the host reports (``prompt_tokens_details``.
    ``cached_tokens``) is the cache-read count — there is no cache-creation
    analog on this API, so that field stays zero. A response without usage
    parses to ``None`` → the debit is 0 (the existing rule).
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cache_read_input_tokens=_cached_tokens(usage) or 0,
    )


def _text_of(response: Any) -> str:
    """The first choice's reply text, or ``""`` when the reply carries none."""
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return ""
    content = getattr(getattr(choices[0], "message", None), "content", None)
    return content if isinstance(content, str) else ""


def _parse_answer(
    text: str, evidence: Sequence[Evidence], *, model: str, usage: TokenUsage | None
) -> GeneratedAnswer:
    """Parse a reply into a ``GeneratedAnswer`` (shared by both call paths).

    Marker *n* resolves to ``evidence[n-1]``'s chunk id, in first-occurrence
    order and deduped — the same walk discipline as the Citations adapter. An
    out-of-range marker names no chunk: no chunk, no citation. The reply text is
    kept exactly as written (the marks are the reader's citation display, and
    history strips them); no span is ever reported, because a prompt-cited reply
    carries no honest character offsets. The sentinel comparison deliberately
    runs on the *unmarked* text, so no marker can turn a decline into an answer:
    a whole-reply sentinel is ``found=False`` with empty text and citations,
    while an embedded occurrence stays prose.
    """
    if CITATION_MARKER_RE.sub("", text).strip() == SENTINEL:
        return GeneratedAnswer(text="", cited_chunk_ids=(), model=model, found=False, usage=usage)
    cited: list[UUID] = []
    seen: set[int] = set()
    for match in CITATION_MARKER_RE.finditer(text):
        number = int(match.group()[2:-1])
        if not 1 <= number <= len(evidence) or number in seen:
            continue
        seen.add(number)
        cited.append(evidence[number - 1].chunk_id)
    return GeneratedAnswer(
        text=text,
        cited_chunk_ids=tuple(cited),
        model=model,
        found=True,
        usage=usage,
    )


def _log_call(usage: Any, *, model: str, found: bool) -> None:
    """Emit one content-free log line per call — usage counts and outcome only.

    ``usage`` is the provider's usage-shaped object when the call reported one
    (the buffered response's ``.usage``, or the final stream chunk's), else
    ``None`` — every field reads as ``None`` then, which is the honest line.
    """
    logger.info(
        "openai-compatible generation model=%s input_tokens=%s output_tokens=%s "
        "cached_input_tokens=%s found=%s",
        model,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        _cached_tokens(usage),
        found,
    )


def _log_client_error(exc: BaseException) -> None:
    """Emit one redacted line naming the request shape a provider 4xx rejected.

    The exception's own message quotes the offending request back — documents,
    system prompt, and the learner's question — so logging it would put learner
    content in the log (NFR-SEC-004). Shape and status alone already narrow the
    cause; anything without a 4xx status passes through unlogged as the
    transport failure it is.
    """
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int) or not 400 <= status < 500:
        return
    logger.warning(
        "openai-compatible generation rejected request_shape=%s status=%s request_id=%s",
        _REQUEST_SHAPE,
        status,
        getattr(exc, "request_id", None),
    )


def _raise_translated(exc: BaseException) -> NoReturn:
    """Re-raise a caught provider failure as its Learny taxonomy class (TAX-02).

    The SDK-specific branch is exactly this binding: the providers package's
    shared translator (:func:`app.infrastructure.providers.translation.
    raise_translated`) owns the status/timeout classification, the cause
    chaining, and the identity-preserved passthrough — this adapter supplies the
    OpenAI SDK's own timeout and connection-error types as its inputs. The
    messages on the translated errors name the failure class and status only,
    never the SDK's exception message (NFR-SEC-004).
    """
    import openai  # local import — the sole SDK reference (ADR-0007/0009)

    _raise_translated_shared(
        exc,
        timeout_exceptions=(openai.APITimeoutError,),
        unreachable_exceptions=(openai.APIConnectionError,),
    )


class OpenAICompatibleGenerationAdapter:
    """``GenerationPort`` implementation over any OpenAI-compatible chat API.

    Constructed with the API key, model id, the host's ``base_url``, and the
    ``max_tokens`` budget the composition root read from the serving profile.
    The profile's per-mode effort values are accepted and deliberately ignored —
    this kind cannot express them, and that is a declared degradation, not an
    error (ECON-05): no effort/thinking parameter ever enters a request body.
    The real ``openai.OpenAI`` client is built lazily on first use (so the SDK
    import stays inside this module and an injected fake needs no key/network);
    tests pass a ``client`` directly.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        base_url: str = "",
        effort_ask: str = "medium",
        effort_teach: str = "medium",
        client: _ChatClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._max_tokens = max_tokens
        # Accepted and recorded, never sent (ECON-05): reading them back is for
        # introspection and tests, and the absence of an effort key in the
        # captured request body is the contract.
        self._effort_ask = effort_ask
        self._effort_teach = effort_teach
        self._client = client

    @property
    def model(self) -> str:
        """Stable model identity, readable without a ``generate`` call (QA-04)."""
        return self._model

    def _get_client(self) -> _ChatClient:
        """Return the injected client, or lazily build ``openai.OpenAI``."""
        if self._client is None:
            import openai  # local import — the sole SDK reference (ADR-0007/0009)

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url or None)
        return self._client

    def _request(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn],
        target_section_path: tuple[str, ...] | None,
        tutor_phase: str | None,
        hint_level: str | None,
    ) -> dict[str, Any]:
        """The shared create-call kwargs — one request shape for both paths."""
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": _build_messages(
                message=message,
                mode=mode,
                history=history,
                evidence=evidence,
                target_section_path=target_section_path,
                tutor_phase=tutor_phase,
                hint_level=hint_level,
            ),
            "timeout": _GENERATE_TIMEOUT_S,
        }

    def generate(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> GeneratedAnswer:
        """Generate a prompt-cited response grounded in ``evidence`` (single-shot)."""
        try:
            response = self._get_client().chat.completions.create(
                **self._request(
                    message=message,
                    mode=mode,
                    evidence=evidence,
                    history=history,
                    target_section_path=target_section_path,
                    tutor_phase=tutor_phase,
                    hint_level=hint_level,
                )
            )
        except Exception as exc:
            _log_client_error(exc)
            _raise_translated(exc)
        answer = _parse_answer(
            _text_of(response), evidence, model=self._model, usage=_usage_of(response)
        )
        _log_call(getattr(response, "usage", None), model=self._model, found=answer.found)
        return answer

    def generate_stream(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the same response: raw text deltas, then the authoritative event.

        The create call carries ``stream_options={"include_usage": True}`` so a
        host that honors it rides the usage on a final choice-less chunk (the
        last usage seen wins); a host that ignores it produces no usage → the
        completed answer's usage is ``None`` → the debit is 0 — the declared
        degradation (ECON-03). Text deltas pass through **raw**, markers and all,
        exactly as the Citations adapter streams its block text; the sentinel
        hold-back that keeps a not-found reply from ever reaching a client lives
        in the application stream path and is provider-independent. The
        authoritative :class:`~app.domain.entities.AnswerCompleted` is parsed
        from the **accumulated** text with the shared parser, so a marker split
        across chunks parses whole and the completed answer is byte-identical to
        the buffered one. A failure before the first delta raises the translated
        error (what makes this adapter a legal router fail-over candidate);
        after a delta is out the failure still translates, but no router may
        rewind it (ROUTE-04). The ``finally`` closes the SDK stream, so a
        consumer disconnect never leaks a provider generation.
        """
        request = self._request(
            message=message,
            mode=mode,
            evidence=evidence,
            history=history,
            target_section_path=target_section_path,
            tutor_phase=tutor_phase,
            hint_level=hint_level,
        )
        # A stream proves progress as frames arrive — deliberately unbounded, and
        # the usage request is the one streaming-only parameter.
        del request["timeout"]
        request["stream"] = True
        request["stream_options"] = {"include_usage": True}
        return self._stream_events(request, evidence)

    def _stream_events(
        self, request: dict[str, Any], evidence: Sequence[Evidence]
    ) -> Iterator[AnswerStreamEvent]:
        """Drive one streaming create call, translating failures on the way out."""
        accumulated: list[str] = []
        usage: TokenUsage | None = None
        reported: Any = None
        try:
            stream = self._get_client().chat.completions.create(**request)
            try:
                for chunk in stream:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        reported = chunk_usage
                        usage = _usage_of(chunk)
                    choices = getattr(chunk, "choices", None) or ()
                    if not choices:
                        continue
                    content = getattr(getattr(choices[0], "delta", None), "content", None)
                    if isinstance(content, str) and content:
                        accumulated.append(content)
                        yield AnswerTextDelta(text=content)
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
        except Exception as exc:
            _log_client_error(exc)
            _raise_translated(exc)
        answer = _parse_answer("".join(accumulated), evidence, model=self._model, usage=usage)
        _log_call(reported, model=self._model, found=answer.found)
        yield AnswerCompleted(answer=answer)
