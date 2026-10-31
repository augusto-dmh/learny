"""Drift sensor — the local-models operator runbook and its wiring stay present.

Documentation deliverables for the self-host local-model profile: the runbook
(``docs/ops/local-models.md``) carries every operator-profile anchor, the env
examples carry the compat embedding wiring with its self-host-only boundary in
the amendment's words, and the golden-capture procedure stands recorded with
its honest operator gate. Content is asserted, not executed (the
``test_ops_docs`` pattern).
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_RUNBOOK = _REPO / "docs" / "ops" / "local-models.md"
_ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
_ENV_PROD = Path(__file__).resolve().parents[1] / ".env.production.example"
_AMENDMENT = (
    _REPO / "docs" / "adr" / "0019-use-openai-embeddings-with-per-chunk-model-versioning.md"
)


def _collapsed(text: str) -> str:
    """One-line view of a document, so a hard-wrapped sentence still matches."""
    return " ".join(text.split())


def test_runbook_exists() -> None:
    assert _RUNBOOK.is_file()


def test_operator_profile_anchors() -> None:
    # The two documented endpoints, the placeholder-key convention, zero prices,
    # the prompt-cited declaration, mode eligibility, and the self-host-only
    # embedding boundary — each a required anchor of the operator profile.
    text = _collapsed(_RUNBOOK.read_text(encoding="utf-8"))
    for anchor in (
        "http://localhost:11434/v1",
        "http://localhost:1234/v1",
        "LEARNY_GENERATION_PROFILES",
        "openai-compatible",
        "api_key_env",
        "placeholder",
        '"price_input_usd_per_million_tokens": 0',
        '"grounding": "prompt-cited"',
        '"ask_enabled": true',
        '"teach_enabled": true',
        "self-host only",
        "lexical-only",
        "reembed.document",
        "app.cli.embedding_status",
    ):
        assert anchor in text, f"runbook lost its anchor: {anchor}"


def test_pt_br_evidence_position() -> None:
    # The honest evidence position: no quality claim without a recorded capture.
    text = _collapsed(_RUNBOOK.read_text(encoding="utf-8"))
    assert "unproven for cited pt-BR answers" in text
    assert "operator-gated" in text
    assert "evals/local/" in text
    assert "capture_local_golden" in text


def test_capture_procedure_and_operator_gate() -> None:
    # The exact capture procedure an operator runs, the plainly stated reason
    # the reference capture is not recorded (never faked), and the guarantee
    # that the hosted key is never forwarded to the runtime the capture names.
    text = _collapsed(_RUNBOOK.read_text(encoding="utf-8"))
    assert "--base-url http://localhost:11434/v1" in text
    assert "--model" in text
    assert "JSONL" in text
    assert "no local runtime on the development machine" in text
    assert "never fakes" in text
    assert "never forwarded" in text


def test_env_examples_document_compat_wiring() -> None:
    # Both env examples carry the third provider value, the base URL variable,
    # and the self-host-only boundary in the amendment's words.
    amendment = _collapsed(_AMENDMENT.read_text(encoding="utf-8"))
    assert "Self-host local embeddings" in amendment
    boundary = "lexical-only until re-embedded"
    assert boundary in amendment

    for env in (_ENV_EXAMPLE, _ENV_PROD):
        text = _collapsed(env.read_text(encoding="utf-8").replace("#", " "))
        assert "openai-compatible" in text, f"{env.name} lost the provider value"
        assert "LEARNY_EMBEDDING_BASE_URL" in text, f"{env.name} lost the base URL"
        assert "SELF-HOST ONLY" in text, f"{env.name} lost the boundary"
        assert boundary in text, f"{env.name} lost the amendment's words"
        assert "docs/ops/local-models.md" in text, f"{env.name} lost the runbook link"
