"""LLM-as-judge harness for generation quality (design §8, research §4).

Two judge calls per case on ``settings.judge_model`` — **faithfulness** (extract
the answer's claims, label each SUPPORTED/UNSUPPORTED, aggregate to a supported
ratio) and **answer relevancy** (1-5) — both via structured outputs
(``output_config.format`` json_schema) so the reply parses deterministically. The
judge sees plain-text evidence, never citations-enabled ``document`` blocks, so
structured outputs are legal (the Citations API and structured outputs are
mutually exclusive). ``run_eval`` caps the case count and appends one JSONL line
per case to ``evals/results/<date>-<git-sha>.jsonl``; aggregate thresholds are
asserted only when ``LEARNY_EVAL_GATE=1`` (calibration-first — the thresholds and
the flag are both set from the first observed baselines, research §5/§8).

The ``anthropic`` SDK is imported lazily inside :meth:`Judge._get_client` only, so
an injected fake client needs no key or network (mirrors the answer adapter).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

_HERE = Path(__file__).resolve().parent
# judge.py → app/eval → app → backend → repo root; results live at the repo root so
# the test run (from backend/) and the workflow's artifact upload agree on the path.
_REPO_ROOT = _HERE.parents[2]
RESULTS_DIR = _REPO_ROOT / "evals" / "results"

FAITHFULNESS_PROMPT_PATH = _HERE / "prompts" / "faithfulness.md"
RELEVANCY_PROMPT_PATH = _HERE / "prompts" / "relevancy.md"

# Judge output is short (a claim list or one integer); bound it well below the
# non-streaming guard so the fake client stays a plain object.
_JUDGE_MAX_TOKENS = 1024

# Aggregate gate thresholds — asserted only when LEARNY_EVAL_GATE=1. Provisional
# literature defaults (research §4); recalibrate from the first observed baselines
# before enabling the gate (research §5/§8: literature numbers are not Learny-
# calibrated, so the default is report-only).
FAITHFULNESS_MIN = 0.75
RELEVANCY_MIN = 4.0

_FAITHFULNESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "supported": {"type": "boolean"},
                },
                "required": ["claim", "supported"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

_RELEVANCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"score": {"type": "integer", "enum": [1, 2, 3, 4, 5]}},
    "required": ["score"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Claim:
    """One factual claim extracted from an answer plus its faithfulness label."""

    claim: str
    supported: bool


@dataclass(frozen=True)
class FaithfulnessResult:
    """The faithfulness judgement: the labeled claims and their supported ratio."""

    claims: tuple[Claim, ...]

    @property
    def supported_ratio(self) -> float:
        """Fraction of claims the judge marked SUPPORTED; ``1.0`` when there are none.

        An answer with no factual claims (e.g. a not-found decline) is vacuously
        faithful — nothing unsupported was asserted.
        """
        if not self.claims:
            return 1.0
        supported = sum(1 for claim in self.claims if claim.supported)
        return supported / len(self.claims)


@dataclass(frozen=True)
class EvalInput:
    """One case's generation, ready for the judge (provider/DB-agnostic).

    ``evidence_text`` is the plain-text passages the answer was grounded in (no
    citations-enabled documents — structured outputs would 400 otherwise);
    ``citation_valid`` is the deterministic invariant result carried through to the
    JSONL line and the gate.
    """

    case_id: str
    question: str
    evidence_text: str
    answer_text: str
    generation_model: str
    citation_valid: bool


class _MessagesClient(Protocol):
    """The narrow slice of the Anthropic client the judge uses (test seam)."""

    messages: Any


class Judge:
    """Scores generation output with the configured judge model (structured outputs).

    Constructed with the API key and judge model id; the real ``anthropic.Anthropic``
    client is built lazily on first use so an injected fake needs no key/network.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: _MessagesClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    @property
    def model(self) -> str:
        """The judge model id (readable without a call)."""
        return self._model

    def _get_client(self) -> _MessagesClient:
        if self._client is None:
            import anthropic  # local import — the sole SDK reference (ADR-0007/0009)

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _judge(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """One structured-outputs judge call → the parsed JSON object."""
        message = self._get_client().messages.create(
            model=self._model,
            max_tokens=_JUDGE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(_first_text(message))

    def faithfulness(
        self, *, question: str, evidence: str, answer: str
    ) -> FaithfulnessResult:
        """Extract the answer's claims and label each SUPPORTED/UNSUPPORTED."""
        data = self._judge(
            system=FAITHFULNESS_PROMPT_PATH.read_text(encoding="utf-8"),
            user=_faithfulness_user(question, evidence, answer),
            schema=_FAITHFULNESS_SCHEMA,
        )
        claims = tuple(
            Claim(claim=item["claim"], supported=bool(item["supported"]))
            for item in data["claims"]
        )
        return FaithfulnessResult(claims=claims)

    def relevancy(self, *, question: str, answer: str) -> int:
        """Score how well the answer addresses the question (integer 1-5)."""
        data = self._judge(
            system=RELEVANCY_PROMPT_PATH.read_text(encoding="utf-8"),
            user=_relevancy_user(question, answer),
            schema=_RELEVANCY_SCHEMA,
        )
        return int(data["score"])


def _first_text(message: Any) -> str:
    """Return the first ``text`` block's text from a Claude message."""
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("judge response contained no text block")


def _faithfulness_user(question: str, evidence: str, answer: str) -> str:
    return f"QUESTION:\n{question}\n\nSOURCE PASSAGES:\n{evidence}\n\nANSWER:\n{answer}"


def _relevancy_user(question: str, answer: str) -> str:
    return f"QUESTION:\n{question}\n\nANSWER:\n{answer}"


def prompt_hash() -> str:
    """sha256 of the judge prompt files — versions the results by judge prompt."""
    digest = hashlib.sha256()
    digest.update(FAITHFULNESS_PROMPT_PATH.read_bytes())
    digest.update(RELEVANCY_PROMPT_PATH.read_bytes())
    return digest.hexdigest()


def _git_sha() -> str:
    """Short git sha for the results filename / line; env first, then git, else 'unknown'."""
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_eval(
    inputs: Sequence[EvalInput],
    *,
    judge: Judge,
    max_cases: int,
    results_dir: Path = RESULTS_DIR,
    gate: bool | None = None,
) -> list[dict[str, Any]]:
    """Judge up to ``max_cases`` cases, append a JSONL line each, optionally gate.

    Caps the case count first (cost bound, research §8), scores faithfulness and
    relevancy per case, and writes ``evals/results/<date>-<git-sha>.jsonl`` with one
    line per case: ``{case_id, ts, git_sha, generation_model, judge_model,
    prompt_hash, faithfulness, relevancy, citation_valid}``. When ``gate`` is true
    (defaults to ``LEARNY_EVAL_GATE=1``) the aggregate thresholds are asserted;
    otherwise the run is report-only (calibration-first). Returns the written lines.
    """
    if gate is None:
        gate = os.getenv("LEARNY_EVAL_GATE") == "1"

    git_sha = _git_sha()
    phash = prompt_hash()
    capped = list(inputs[:max_cases])
    lines: list[dict[str, Any]] = []
    for item in capped:
        faithfulness = judge.faithfulness(
            question=item.question, evidence=item.evidence_text, answer=item.answer_text
        )
        relevancy = judge.relevancy(question=item.question, answer=item.answer_text)
        lines.append(
            {
                "case_id": item.case_id,
                "ts": datetime.now(UTC).isoformat(),
                "git_sha": git_sha,
                "generation_model": item.generation_model,
                "judge_model": judge.model,
                "prompt_hash": phash,
                "faithfulness": faithfulness.supported_ratio,
                "relevancy": relevancy,
                "citation_valid": item.citation_valid,
            }
        )

    _write_jsonl(lines, results_dir=results_dir, git_sha=git_sha)

    if gate:
        _assert_aggregates(lines)
    return lines


def _write_jsonl(
    lines: Sequence[dict[str, Any]], *, results_dir: Path, git_sha: str
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    path = results_dir / f"{date}-{git_sha}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, sort_keys=True) + "\n")
    return path


def _assert_aggregates(lines: Sequence[dict[str, Any]]) -> None:
    """Enforce the aggregate thresholds (mean faithfulness/relevancy + citations)."""
    if not lines:
        return
    mean_faithfulness = sum(line["faithfulness"] for line in lines) / len(lines)
    mean_relevancy = sum(line["relevancy"] for line in lines) / len(lines)
    assert all(line["citation_valid"] for line in lines), "a case failed citation validity"
    assert mean_faithfulness >= FAITHFULNESS_MIN, (
        f"mean faithfulness {mean_faithfulness:.3f} < {FAITHFULNESS_MIN}"
    )
    assert mean_relevancy >= RELEVANCY_MIN, (
        f"mean relevancy {mean_relevancy:.3f} < {RELEVANCY_MIN}"
    )
