"""F2 gate — quiz answerability judge (offline unit + live nightly, QUIZ-24).

Offline (PR suite, fake client, no network): the answerability prompt loads and is
versioned by its own sha256; ``Judge.answerability`` parses the structured-outputs
schema into an :class:`AnswerabilityResult`; ``run_answerability_eval`` writes one
JSONL line per item with the full schema and caps at ``max_cases``.

Live (``live and eval``, skipped without a key — the nightly ``eval.yml`` picks it up
by that marker expression unchanged): generate deterministic quiz items from the
golden book and score whether each is answerable from its cited excerpt alone with
the real judge model, writing the results JSONL the workflow uploads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.entities import QuizSection
from app.eval.judge import (
    AnswerabilityInput,
    AnswerabilityResult,
    Judge,
    answerability_prompt_hash,
    run_answerability_eval,
)
from app.infrastructure.quiz.local import DeterministicQuizAdapter
from tests.golden_corpus import EXPECTED_GOLDEN_SECTIONS

_JUDGE_MODEL = "claude-haiku-4-5"


# --- Fake Anthropic client: returns a canned JSON payload as one text block ------


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, payload: dict) -> None:
        self.content = [_FakeTextBlock(json.dumps(payload))]


class _FakeMessagesResource:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeMessage:
        self.calls.append(kwargs)
        return _FakeMessage(self._payloads.pop(0))


class _FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.messages = _FakeMessagesResource(payloads)


def _judge(payloads: list[dict]) -> tuple[Judge, _FakeClient]:
    client = _FakeClient(payloads)
    return Judge(api_key="unused-fake", model=_JUDGE_MODEL, client=client), client


# --- Prompt loading + versioning (QUIZ-24) -------------------------------------


def test_answerability_prompt_loads_and_is_versioned() -> None:
    phash = answerability_prompt_hash()

    # A stable sha256 hex over the committed prompt file — the eval's own version key.
    assert len(phash) == 64
    assert all(c in "0123456789abcdef" for c in phash)


# --- Structured-outputs result mapping (QUIZ-24) -------------------------------


def test_answerability_parses_structured_result() -> None:
    judge, client = _judge(
        [{"answerable": True, "score": 5, "reason": "the excerpt states it"}]
    )

    result = judge.answerability(
        question="What pulls seawater?", answer="the moon's gravity", excerpt="e"
    )

    assert isinstance(result, AnswerabilityResult)
    assert result.answerable is True
    assert result.score == 5
    assert result.reason == "the excerpt states it"
    # The judge call carried the answerability json_schema, no citations documents.
    call = client.messages.calls[0]
    assert call["model"] == _JUDGE_MODEL
    schema = call["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"answerable", "score", "reason"}
    assert schema["properties"]["score"]["enum"] == [1, 2, 3, 4, 5]


def test_answerability_maps_negative_judgement() -> None:
    judge, _ = _judge(
        [{"answerable": False, "score": 1, "reason": "needs outside knowledge"}]
    )

    result = judge.answerability(question="q", answer="a", excerpt="unrelated")

    assert result.answerable is False
    assert result.score == 1
    assert result.reason == "needs outside knowledge"


# --- JSONL results + cap (QUIZ-24) ---------------------------------------------


def _inputs(n: int) -> list[AnswerabilityInput]:
    return [
        AnswerabilityInput(
            item_id=f"item-{i}",
            question=f"q{i}",
            answer=f"a{i}",
            excerpt=f"e{i}",
        )
        for i in range(n)
    ]


def test_run_answerability_eval_writes_jsonl_line_per_item(tmp_path: Path) -> None:
    judge, _ = _judge(
        [
            {"answerable": True, "score": 5, "reason": "r0"},
            {"answerable": False, "score": 2, "reason": "r1"},
        ]
    )

    lines = run_answerability_eval(_inputs(2), judge=judge, max_cases=10, results_dir=tmp_path)

    assert len(lines) == 2
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    written = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(written) == 2
    first = written[0]
    assert set(first) == {
        "item_id",
        "ts",
        "git_sha",
        "judge_model",
        "prompt_hash",
        "answerable",
        "score",
        "reason",
    }
    assert first["item_id"] == "item-0"
    assert first["judge_model"] == _JUDGE_MODEL
    assert first["prompt_hash"] == answerability_prompt_hash()
    assert first["answerable"] is True
    assert first["score"] == 5
    assert first["reason"] == "r0"
    assert written[1]["answerable"] is False
    assert written[1]["score"] == 2


def test_run_answerability_eval_caps_at_max_cases(tmp_path: Path) -> None:
    judge, client = _judge(
        [{"answerable": True, "score": 5, "reason": "r"} for _ in range(2)]
    )

    lines = run_answerability_eval(_inputs(5), judge=judge, max_cases=2, results_dir=tmp_path)

    assert len(lines) == 2
    assert len(client.messages.calls) == 2  # never judged the remaining three


# --- Live answerability round-trip (nightly judge tier) — skipped without a key -


def _golden_answerability_inputs() -> list[AnswerabilityInput]:
    """Deterministic quiz items generated from the golden book (offline generation)."""
    sections = tuple(
        QuizSection(
            section_path=spec["section_path"],
            anchor=spec["anchor"],
            title=spec["section_path"][-1],
            chunks=tuple((uuid4(), text) for text in spec["chunk_texts"]),
        )
        for spec in EXPECTED_GOLDEN_SECTIONS
    )
    adapter = DeterministicQuizAdapter()
    result = adapter.collect_deck(adapter.begin_deck(sections))
    assert result is not None
    return [
        AnswerabilityInput(
            item_id=f"{candidate.item_type}-{index}",
            question=candidate.question,
            answer=candidate.answer,
            excerpt=candidate.anchor_quote,
        )
        for index, candidate in enumerate(result.candidates)
    ]


@pytest.mark.live
@pytest.mark.eval
@pytest.mark.skipif(
    not os.getenv("LEARNY_ANTHROPIC_API_KEY"),
    reason="LEARNY_ANTHROPIC_API_KEY unset — live answerability judge skipped (CI stays offline)",
)
def test_live_answerability_scores_golden_items() -> None:
    # Writes to the real evals/results/ dir (the default) so the nightly run produces
    # the results JSONL the workflow uploads. Live-only, so an offline run never
    # touches the repo tree.
    from app.core.config import get_settings

    settings = get_settings()
    judge = Judge(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"], model=settings.judge_model
    )
    inputs = _golden_answerability_inputs()
    assert inputs  # the golden book yields items to judge

    lines = run_answerability_eval(inputs, judge=judge, max_cases=settings.eval_max_cases)

    assert 1 <= len(lines) <= len(inputs)
    for line in lines:
        assert isinstance(line["answerable"], bool)
        assert line["score"] in range(1, 6)
        assert line["reason"]
