"""Embedding-provider settings — defaults and environment overrides (EMB-06).

The composition-root factory reads these four knobs to select and build the
embedding adapter, so their defaults (offline ``local`` provider, no key required)
and ``LEARNY_``-prefixed overrides are pinned here. ``Settings`` is instantiated
directly (bypassing the ``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

from app.core.config import Settings


def test_embedding_settings_defaults() -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "local"
    assert settings.openai_api_key == ""
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dim == 1536


def test_embedding_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every embedding knob.
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("LEARNY_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("LEARNY_EMBEDDING_DIM", "512")

    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "openai"
    assert settings.openai_api_key == "sk-test-123"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dim == 512


def test_generation_settings_defaults() -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    settings = Settings(_env_file=None)

    assert settings.generation_provider == "local"
    assert settings.anthropic_api_key == ""
    assert settings.generation_model == "claude-sonnet-5"
    assert settings.generation_max_tokens == 1024
    assert settings.judge_model == "claude-haiku-4-5"
    assert settings.eval_max_cases == 50


def test_generation_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every generation knob.
    monkeypatch.setenv("LEARNY_GENERATION_PROVIDER", "anthropic")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "sk-ant-123")
    monkeypatch.setenv("LEARNY_GENERATION_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("LEARNY_GENERATION_MAX_TOKENS", "2048")
    monkeypatch.setenv("LEARNY_JUDGE_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("LEARNY_EVAL_MAX_CASES", "10")

    settings = Settings(_env_file=None)

    assert settings.generation_provider == "anthropic"
    assert settings.anthropic_api_key == "sk-ant-123"
    assert settings.generation_model == "claude-opus-4-8"
    assert settings.generation_max_tokens == 2048
    assert settings.judge_model == "claude-sonnet-4-6"
    assert settings.eval_max_cases == 10


def test_quiz_settings_defaults() -> None:
    # Design defaults (design §Settings additions): batched Haiku model, density caps,
    # dedup threshold, and batch polling bounds — CI needs no key (local adapter).
    settings = Settings(_env_file=None)

    assert settings.quiz_model == "claude-haiku-4-5"
    assert settings.quiz_max_items_per_section == 6
    assert settings.quiz_min_section_chars == 200
    assert settings.quiz_dedup_threshold == 0.90
    assert settings.quiz_batch_timeout_s == 3600
    assert settings.quiz_batch_poll_interval_s == 30


def test_quiz_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every quiz knob.
    monkeypatch.setenv("LEARNY_QUIZ_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("LEARNY_QUIZ_MAX_ITEMS_PER_SECTION", "4")
    monkeypatch.setenv("LEARNY_QUIZ_MIN_SECTION_CHARS", "500")
    monkeypatch.setenv("LEARNY_QUIZ_DEDUP_THRESHOLD", "0.85")
    monkeypatch.setenv("LEARNY_QUIZ_BATCH_TIMEOUT_S", "7200")
    monkeypatch.setenv("LEARNY_QUIZ_BATCH_POLL_INTERVAL_S", "15")

    settings = Settings(_env_file=None)

    assert settings.quiz_model == "claude-opus-4-8"
    assert settings.quiz_max_items_per_section == 4
    assert settings.quiz_min_section_chars == 500
    assert settings.quiz_dedup_threshold == 0.85
    assert settings.quiz_batch_timeout_s == 7200
    assert settings.quiz_batch_poll_interval_s == 15


def test_pdf_ocr_settings_defaults() -> None:
    # OCR on by default with the author-corpus language pair (spec: enabled=true,
    # langs "en,pt"); the parsed list mirrors the raw value.
    settings = Settings(_env_file=None)

    assert settings.pdf_ocr_enabled is True
    assert settings.pdf_ocr_langs == "en,pt"
    assert settings.pdf_ocr_lang_list() == ("en", "pt")


def test_pdf_ocr_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_PDF_OCR_ENABLED", "false")
    monkeypatch.setenv("LEARNY_PDF_OCR_LANGS", "pt")

    settings = Settings(_env_file=None)

    assert settings.pdf_ocr_enabled is False
    assert settings.pdf_ocr_lang_list() == ("pt",)


def test_pdf_ocr_langs_are_trimmed_and_empties_dropped() -> None:
    # Malformed entries (spaces, empty items) are normalized away.
    settings = Settings(_env_file=None, pdf_ocr_langs=" en , ,pt, ")

    assert settings.pdf_ocr_lang_list() == ("en", "pt")


def test_pdf_ocr_langs_fall_back_to_the_default_pair_when_empty() -> None:
    # A value with no usable entries must not configure OCR with zero languages.
    settings = Settings(_env_file=None, pdf_ocr_langs=" , ,")

    assert settings.pdf_ocr_lang_list() == ("en", "pt")


def test_fsrs_settings_defaults() -> None:
    # FSRS-6 population defaults; fuzzing on by default (tests disable it explicitly).
    settings = Settings(_env_file=None)

    assert settings.fsrs_desired_retention == 0.9
    assert settings.fsrs_fuzzing is True


def test_fsrs_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_FSRS_DESIRED_RETENTION", "0.85")
    monkeypatch.setenv("LEARNY_FSRS_FUZZING", "false")

    settings = Settings(_env_file=None)

    assert settings.fsrs_desired_retention == 0.85
    assert settings.fsrs_fuzzing is False


def test_notes_settings_default() -> None:
    # Note-body cap default (NF-04); enforced by the note use cases before any write.
    settings = Settings(_env_file=None)

    assert settings.notes_max_body_chars == 100000


def test_notes_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_NOTES_MAX_BODY_CHARS", "500")

    settings = Settings(_env_file=None)

    assert settings.notes_max_body_chars == 500
