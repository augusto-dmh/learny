"""Embedding-provider settings — defaults and environment overrides (EMB-06).

The composition-root factory reads these four knobs to select and build the
embedding adapter, so their defaults (offline ``local`` provider, no key required)
and ``LEARNY_``-prefixed overrides are pinned here. ``Settings`` is instantiated
directly (bypassing the ``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import _RETIRED_KNOBS, Settings
from app.core.instrumentation import InstrumentRecorder

_ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

_INSTRUMENT_VARS = (
    "LEARNY_DEV_INSTRUMENT_ENABLED",
    "LEARNY_INSTRUMENT_CAPACITY",
    "LEARNY_SLOW_QUERY_MS",
    "LEARNY_SLOW_QUERY_STATEMENT_CHARS",
)

_CONVERSATION_VARS = (
    "LEARNY_CONVERSATION_EVIDENCE_TOP_K",
    "LEARNY_CONVERSATION_HISTORY_TURNS",
    "LEARNY_CONVERSATION_MESSAGE_MAX_CHARS",
    "LEARNY_CONVERSATION_SCOPE_MAX_ANCHORS",
    "LEARNY_CONVERSATION_SCOPE_ANCHOR_MAX_CHARS",
)


def test_embedding_settings_defaults(monkeypatch) -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    # Clear the suite-wide provider pin so this asserts the field default, not the
    # injected env value (Settings(_env_file=None) still reads os.environ).
    monkeypatch.delenv("LEARNY_EMBEDDING_PROVIDER", raising=False)
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


def test_generation_settings_defaults(monkeypatch) -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    # Clear the suite-wide provider pin so this asserts the field default, not the
    # injected env value (Settings(_env_file=None) still reads os.environ).
    monkeypatch.delenv("LEARNY_GENERATION_PROVIDER", raising=False)
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
    assert settings.quiz_max_suggestions == 3
    assert settings.quiz_max_card_chars == 2000
    assert settings.quiz_min_section_chars == 200
    assert settings.quiz_dedup_threshold == 0.90
    assert settings.quiz_batch_timeout_s == 3600
    assert settings.quiz_batch_poll_interval_s == 30


def test_quiz_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every quiz knob.
    monkeypatch.setenv("LEARNY_QUIZ_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("LEARNY_QUIZ_MAX_ITEMS_PER_SECTION", "4")
    monkeypatch.setenv("LEARNY_QUIZ_MAX_SUGGESTIONS", "5")
    monkeypatch.setenv("LEARNY_QUIZ_MAX_CARD_CHARS", "500")
    monkeypatch.setenv("LEARNY_QUIZ_MIN_SECTION_CHARS", "500")
    monkeypatch.setenv("LEARNY_QUIZ_DEDUP_THRESHOLD", "0.85")
    monkeypatch.setenv("LEARNY_QUIZ_BATCH_TIMEOUT_S", "7200")
    monkeypatch.setenv("LEARNY_QUIZ_BATCH_POLL_INTERVAL_S", "15")

    settings = Settings(_env_file=None)

    assert settings.quiz_model == "claude-opus-4-8"
    assert settings.quiz_max_items_per_section == 4
    assert settings.quiz_max_suggestions == 5
    assert settings.quiz_max_card_chars == 500
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


def test_instrument_settings_defaults(monkeypatch) -> None:
    # The dev surface is off unless deliberately enabled, and the recorder bounds
    # plus the slow-query threshold carry their documented defaults. The env is
    # neutralized first: Settings(_env_file=None) still reads os.environ, so a
    # local .env exported into the shell would otherwise mask the field defaults.
    for name in _INSTRUMENT_VARS:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.dev_instrument_enabled is False
    assert settings.instrument_capacity == 500
    assert settings.slow_query_ms == 200
    assert settings.slow_query_statement_chars == 2000


def test_instrument_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_DEV_INSTRUMENT_ENABLED", "true")
    monkeypatch.setenv("LEARNY_INSTRUMENT_CAPACITY", "50")
    monkeypatch.setenv("LEARNY_SLOW_QUERY_MS", "0")
    monkeypatch.setenv("LEARNY_SLOW_QUERY_STATEMENT_CHARS", "80")

    settings = Settings(_env_file=None)

    assert settings.dev_instrument_enabled is True
    assert settings.instrument_capacity == 50
    # Zero is a legitimate threshold — every statement qualifies, no implicit floor.
    assert settings.slow_query_ms == 0
    assert settings.slow_query_statement_chars == 80


def test_instrument_defaults_match_the_recorder_process_defaults(monkeypatch) -> None:
    # The recorder cannot read settings (an import-time get_settings() call primes
    # the lru-cache Alembic later reads), so its process defaults are written out
    # separately. They must not drift from the documented configuration.
    for name in _INSTRUMENT_VARS:
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    recorder = InstrumentRecorder()

    assert recorder.capacity == settings.instrument_capacity
    assert recorder.statement_max_chars == settings.slow_query_statement_chars


def test_words_per_page_default() -> None:
    # PAGE-01: the page quantum is a backend setting with the documented default, and
    # it is the only definition of the unit — nothing else may carry the number.
    settings = Settings(_env_file=None)

    assert settings.words_per_page == 275


def test_words_per_page_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_WORDS_PER_PAGE", "300")

    settings = Settings(_env_file=None)

    assert settings.words_per_page == 300


def test_conversation_settings_defaults() -> None:
    # One policy for every grounded conversation: the evidence budget handed to
    # scoped retrieval, the prior turns a generation port sees, and the message
    # length the web validator enforces.
    settings = Settings(_env_file=None)

    assert settings.conversation_evidence_top_k == 8
    assert settings.conversation_history_turns == 6
    assert settings.conversation_message_max_chars == 2000
    assert settings.conversation_scope_max_anchors == 100
    assert settings.conversation_scope_anchor_max_chars == 512


def test_conversation_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_CONVERSATION_EVIDENCE_TOP_K", "5")
    monkeypatch.setenv("LEARNY_CONVERSATION_HISTORY_TURNS", "2")
    monkeypatch.setenv("LEARNY_CONVERSATION_MESSAGE_MAX_CHARS", "500")
    monkeypatch.setenv("LEARNY_CONVERSATION_SCOPE_MAX_ANCHORS", "3")
    monkeypatch.setenv("LEARNY_CONVERSATION_SCOPE_ANCHOR_MAX_CHARS", "40")

    settings = Settings(_env_file=None)

    assert settings.conversation_evidence_top_k == 5
    assert settings.conversation_history_turns == 2
    assert settings.conversation_message_max_chars == 500
    assert settings.conversation_scope_max_anchors == 3
    assert settings.conversation_scope_anchor_max_chars == 40


def test_env_example_documents_the_conversation_contract() -> None:
    # An operator tuning the unified surface reads its budgets off the contract:
    # the evidence and history knobs, the message bound, and both scope caps.
    contract = _ENV_EXAMPLE.read_text()

    for name in _CONVERSATION_VARS:
        assert f"\n{name}=" in contract, f"{name} is missing from .env.example"


def test_retired_knobs_are_no_longer_fields(monkeypatch) -> None:
    # The per-surface budgets and length bounds the unified conversation settings
    # replaced are gone, not merely unread — a declared field is a value someone can
    # still reach for and believe in.
    for name in (
        "qa_evidence_top_k",
        "teaching_evidence_top_k",
        "teaching_history_turns",
        "qa_question_max_chars",
        "teaching_message_max_chars",
    ):
        assert name not in Settings.model_fields, name


def test_every_retired_variable_names_a_setting_that_still_exists(monkeypatch) -> None:
    # The warning tells an operator which setting decides the value now. A successor
    # that was itself renamed away would turn that advice into an AttributeError at
    # startup — on the one code path that only runs for the deployments already
    # holding a stale variable.
    settings = Settings(_env_file=None)

    for env_var, successor in _RETIRED_KNOBS.items():
        assert successor in Settings.model_fields, f"{env_var} -> {successor}"
        assert getattr(settings, successor) is not None


def test_a_deployment_still_setting_a_retired_variable_boots(monkeypatch) -> None:
    # Retiring a knob must not take a running deployment down: the variable is
    # simply ignored, and every live setting resolves as it would have anyway.
    for env_var in _RETIRED_KNOBS:
        monkeypatch.setenv(env_var, "3")

    settings = Settings(_env_file=None)

    assert settings.conversation_evidence_top_k == 8
    assert settings.conversation_history_turns == 6
    assert settings.conversation_message_max_chars == 2000


def test_setting_a_retired_knob_warns_once_naming_the_value_in_force(monkeypatch, caplog) -> None:
    # The dangerous failure here is silence: a deployment that tuned one of these
    # still validates, still boots, and quietly serves the new default instead. One
    # warning per variable actually set, naming it and the value now in force, is
    # what reaches the person running the deploy. The variables are read from the
    # environment, so removing the fields did not remove the diagnostic with them.
    monkeypatch.setenv("LEARNY_TEACHING_HISTORY_TURNS", "12")
    monkeypatch.setenv("LEARNY_QA_EVIDENCE_TOP_K", "12")

    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        settings = Settings(_env_file=None)

    warnings = [r.getMessage() for r in caplog.records if r.name == "app.core.config"]
    assert len(warnings) == 2
    assert any(
        "LEARNY_TEACHING_HISTORY_TURNS" in message
        and f"conversation_history_turns={settings.conversation_history_turns}" in message
        for message in warnings
    )
    assert any("LEARNY_QA_EVIDENCE_TOP_K" in message for message in warnings)
    # The knob nobody set is not mentioned.
    assert not any("LEARNY_TEACHING_EVIDENCE_TOP_K" in message for message in warnings)


def test_a_retired_knob_left_in_an_env_file_warns_too(monkeypatch, caplog, tmp_path) -> None:
    # The env file is the other place a value is read from, and ``os.environ`` cannot
    # see it: a knob set there is *more* likely to be believed in, not less, because
    # nothing in the file says it stopped working. A warning that only watched the
    # process environment would go quiet exactly where the operator wrote the tuning.
    for env_var in _RETIRED_KNOBS:
        monkeypatch.delenv(env_var, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LEARNY_TEACHING_HISTORY_TURNS=12\nLEARNY_CONVERSATION_EVIDENCE_TOP_K=4\n")

    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        settings = Settings(_env_file=env_file)

    warnings = [r.getMessage() for r in caplog.records if r.name == "app.core.config"]
    assert len(warnings) == 1
    assert "LEARNY_TEACHING_HISTORY_TURNS" in warnings[0]
    assert f"conversation_history_turns={settings.conversation_history_turns}" in warnings[0]
    # The file is genuinely being read — a live knob beside the dead one took effect,
    # which is what makes the silence about the dead one a defect.
    assert settings.conversation_evidence_top_k == 4


def test_a_retired_knob_in_an_env_file_the_instance_does_not_read_stays_quiet(
    monkeypatch, caplog, tmp_path
) -> None:
    # The warning follows what this instance actually reads: a file it was told to
    # ignore is not a deployment's configuration, and warning about it would train
    # operators (and the suite) to ignore the message.
    for env_var in _RETIRED_KNOBS:
        monkeypatch.delenv(env_var, raising=False)
    (tmp_path / ".env").write_text("LEARNY_TEACHING_HISTORY_TURNS=12\n")

    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(_env_file=None)

    assert [r for r in caplog.records if r.name == "app.core.config"] == []


def test_an_untouched_deployment_gets_no_deprecation_warnings(caplog) -> None:
    # A deployment that never tuned these must boot quietly — a warning nobody can
    # act on is noise that teaches operators to ignore the log.
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(_env_file=None)

    assert [r for r in caplog.records if r.name == "app.core.config"] == []


def test_env_example_documents_the_instrument_contract() -> None:
    # The environment contract is a deliverable: an operator must be able to read
    # the flag, the threshold, the buffer capacity and the statement cap off it.
    contract = _ENV_EXAMPLE.read_text()

    for name in _INSTRUMENT_VARS:
        assert f"\n{name}=" in contract, f"{name} is missing from .env.example"
