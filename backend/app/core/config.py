"""Environment-based application configuration.

Secrets and connection strings come from the environment only (NFR-SEC-003);
nothing here is committed with real values. See `.env.example` for the contract.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource

logger = logging.getLogger(__name__)

# Environment variables the unified conversation settings replaced, mapped to the
# setting that now decides the value. These are no longer fields: ``extra`` is
# ``ignore``, so a deployment that still sets one boots normally — which is exactly
# why the names are kept here. The variable being silently accepted is what makes a
# dead tuning look like a live one, so each one still present in the environment
# earns a startup warning.
_RETIRED_KNOBS = {
    "LEARNY_QA_EVIDENCE_TOP_K": "conversation_evidence_top_k",
    "LEARNY_TEACHING_EVIDENCE_TOP_K": "conversation_evidence_top_k",
    "LEARNY_TEACHING_HISTORY_TURNS": "conversation_history_turns",
    "LEARNY_QA_QUESTION_MAX_CHARS": "conversation_message_max_chars",
    "LEARNY_TEACHING_MESSAGE_MAX_CHARS": "conversation_message_max_chars",
}

# The variable names the env file of the settings instance currently being built
# carries. Set while its sources are assembled and read back by the retired-knob
# warning, which runs later in the same instantiation: the env file resolved for an
# instance (``_env_file`` may override the class default) is knowable only from the
# source that read it, and never reaches the model itself.
_env_file_vars: ContextVar[frozenset[str]] = ContextVar("_env_file_vars", default=frozenset())


class Settings(BaseSettings):
    """Application settings resolved from environment variables.

    Defaults are safe placeholders for local boot; production values are injected
    via the environment (Docker Compose / VPS).
    """

    model_config = SettingsConfigDict(
        env_prefix="LEARNY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "learny-backend"
    environment: str = "local"
    debug: bool = False

    # NOTE: the log format is intentionally NOT a Settings field. It is read
    # directly from ``LEARNY_LOG_FORMAT`` in ``app.core.logging.configure_logging``
    # (single source of truth) so bootstrap logging setup does not prime the
    # ``get_settings`` lru-cache, which Alembic's ``env.py`` later reads.

    # Database (used by /readyz and, later, repositories + migrations)
    database_url: str = "postgresql+psycopg://learny:learny@localhost:5432/learny"

    # Redis / Celery (worker wiring; ingestion tasks land in a later cycle)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    def broker_url(self) -> str:
        """Effective Celery broker URL (falls back to ``redis_url``)."""
        return self.celery_broker_url or self.redis_url

    def result_backend(self) -> str:
        """Effective Celery result backend URL (falls back to ``redis_url``)."""
        return self.celery_result_backend or self.redis_url

    # Session cookie attributes (NFR-SEC-002) — wired fully in Phase C.
    session_cookie_name: str = "learny_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    session_cookie_path: str = "/"

    # CSRF (AD-007) — comma-separated list of trusted browser origins for the
    # Origin/Referer check on state-changing requests. Empty disables the host
    # check (header-token validation still applies); set explicitly in prod.
    csrf_trusted_origins: str = "http://localhost:3000"

    def trusted_origins(self) -> tuple[str, ...]:
        """Parsed, normalized tuple of trusted origins (scheme://host[:port])."""
        return tuple(
            o.strip().rstrip("/") for o in self.csrf_trusted_origins.split(",") if o.strip()
        )

    # Object storage (S3-compatible; MinIO locally, AD-011). Secrets env-only.
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "learny"
    storage_secret_key: str = "learny-dev-secret"
    storage_bucket: str = "learny-sources"
    storage_region: str = "us-east-1"

    # Upload limits (AD-009) — cap the bytes buffered through the request, per
    # format. The web handler reads at most ``max(caps) + 1`` and validation
    # enforces the per-format cap (ING-09/ING-20): EPUB stays at 50 MiB; PDFs are
    # larger on average (born-digital books with images), so the PDF cap is 100 MiB.
    epub_max_bytes: int = 52428800  # 50 MiB
    pdf_max_bytes: int = 104857600  # 100 MiB

    # Ingestion safety — cap the summed *uncompressed* size an EPUB archive may
    # declare before parsing; the upload cap above only bounds compressed bytes,
    # so a crafted archive could otherwise inflate far past it in worker memory.
    epub_max_uncompressed_bytes: int = 524288000  # 500 MiB

    # Figure encode caps — long edge in pixels and encoded WebP payload. Rasters
    # that cannot meet both after downscale are dropped rather than failing ingest.
    media_max_edge_px: int = 1600
    media_max_bytes: int = 1572864

    # Scanned-PDF OCR (ADR-0025) — the Docling adapter retries a textless PDF
    # once with OCR before failing. ``pdf_ocr_enabled`` is the operational
    # kill-switch (False reproduces the OCR-less behavior exactly, for workers
    # whose image lacks the baked OCR models); ``pdf_ocr_langs`` is the
    # comma-separated EasyOCR language list the baked models must cover.
    pdf_ocr_enabled: bool = True
    pdf_ocr_langs: str = "en,pt"

    def pdf_ocr_lang_list(self) -> tuple[str, ...]:
        """The parsed OCR language list (trimmed, empties dropped).

        A malformed value that leaves no usable entries falls back to the
        default pair rather than configuring the OCR engine with zero languages.
        """
        langs = tuple(part.strip() for part in self.pdf_ocr_langs.split(",") if part.strip())
        return langs or ("en", "pt")

    # Worker recovery (RFC-005 Cycle E) — how many times an ingestion job may be
    # claimed before the claim seam terminates it instead of starting another run.
    # The counter is the job's durable ``attempts`` column, not Celery's retry
    # header: a message requeued after its worker died keeps its original delivery
    # headers, so a broker-side counter never advances across those redeliveries
    # and a job that reliably kills its worker would be redelivered forever. Below
    # 1 is rejected here rather than at claim time — it would terminate every job
    # on its first claim, i.e. disable ingestion entirely.
    ingestion_max_attempts: int = Field(default=5, ge=1)

    # Corpus chunking (A-5) — max characters per retrieval chunk before packing
    # starts a new one; oversized single blocks split at sentence boundaries.
    chunk_max_chars: int = 2000

    # Embeddings (ADR-0007/0019) — the provider/model lives only in the adapter;
    # these knobs stay LEARNY_-prefixed and never hard-coded in query/repository
    # code. ``embedding_dim`` is the single source of truth for the vector width: the
    # deterministic adapter derives its ``local-deterministic@{dim}`` identity from
    # it, the OpenAI adapter sends it as the ``dimensions`` request param, and the
    # migration's ``vector(1536)`` column literal must match it (A-1).
    # ``embedding_provider`` selects the adapter at the composition root (``local``
    # default → deterministic, network-free; ``openai`` → the OpenAI adapter built
    # from the key/model/dim below). ``embedding_model`` names the *provider* model —
    # the deterministic adapter ignores it and reports its own identity, so the
    # default is unaffected.
    embedding_dim: int = 1536
    embedding_provider: str = "local"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-large"
    embedding_batch_size: int = 128

    # Hybrid retrieval tuning (ADR-0006) — candidate limits, RRF constant, default
    # and max top-k, and the pgvector HNSW query-time recall knob. All infrastructure
    # tuning, not domain concepts (A-9).
    retrieval_semantic_limit: int = 50
    retrieval_lexical_limit: int = 50
    retrieval_rrf_k: int = 60
    retrieval_top_k: int = 10
    retrieval_max_top_k: int = 50
    hnsw_ef_search: int = 100

    # Notes-in-retrieval arms (ADR-0026 d4, NL-02) — two extra RRF arms over the
    # user's own notes, fused into the same ranking behind ``include_notes``. Smaller
    # per-arm limits than the book arms (the notes corpus is far smaller); weight 1.0
    # is neutral (no eval signal for a bias — the limits are the constraint); the
    # snippet cap bounds how much note body is projected as evidence text.
    retrieval_notes_semantic_limit: int = 5
    retrieval_notes_lexical_limit: int = 5
    retrieval_notes_weight: float = 1.0
    retrieval_notes_snippet_chars: int = 2000

    # Conversations (ADR-0029) — one policy for every grounded conversation,
    # replacing the separate Q&A and teaching knobs it retired. The evidence budget is
    # the ``top_k`` handed to scoped retrieval (keep ≤ ``retrieval_max_top_k``);
    # ``conversation_history_turns`` bounds the prior turns a generation port sees;
    # ``conversation_message_max_chars`` is the message length bound the web
    # validator enforces. The two scope bounds cap the one field a client sizes
    # itself: a scope is re-expanded against the corpus on every turn and is stored
    # for the conversation's life, so an unbounded list would buy durable per-turn
    # work with one request. ``conversation_scope_max_anchors`` caps how many
    # anchors one conversation may name and ``conversation_scope_anchor_max_chars``
    # how long each may be; both are enforced by the web validator.
    conversation_evidence_top_k: int = 8
    conversation_history_turns: int = 6
    conversation_message_max_chars: int = 2000
    conversation_scope_max_anchors: int = 100
    conversation_scope_anchor_max_chars: int = 512
    # Ordinary learner messages in elicit/scaffold before the next tutor generate
    # is forced into the unaided check (AD-293). The policy reads this; the model
    # does not.
    tutor_check_after_turns: int = 3

    # Generation (ADR-0020) — the provider SDK and model names live only in the
    # answer/teaching adapters; these knobs stay LEARNY_-prefixed and never
    # hard-coded in application/domain code. ``generation_provider`` selects the
    # adapter at the composition root (``local`` default → deterministic,
    # network-free; ``anthropic`` → the Claude adapters built from the key/model/
    # max-tokens below), so CI and local development stay offline and key-free.
    # ``anthropic_api_key`` is an env-only secret. ``judge_model`` and
    # ``eval_max_cases`` bound the offline-optional evaluation harness.
    #
    # ``generation_effort`` is how much thinking the model spends before answering;
    # it is a knob rather than a constant because the right value is a live
    # latency/cost trade-off, and a bad value is rejected at startup rather than
    # per request. ``generation_max_tokens`` bounds thinking *and* answer together,
    # so the budget has to hold both.
    generation_provider: str = "local"
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-5"
    generation_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    generation_max_tokens: int = 4096
    judge_model: str = "claude-opus-4-8"
    eval_max_cases: int = 50
    # Modeled-cost ceiling (USD) for operator-triggered live studies: the study
    # runner refuses to start a unit whose modeled cost would cross it (AD-234;
    # the amount is the operator cap set at RFC-005 Cycle B). Modeled, not
    # billed — the runbook's spend report reconciles against actual spend.
    eval_budget_usd: float = 10.0

    # Active recall — quiz deck generation (RFC-002 Cycle E). The provider SDK and
    # model name live only in the quiz adapter; these knobs stay LEARNY_-prefixed and
    # never hard-coded in application/domain code. ``quiz_model`` names the batched
    # generation model (deterministic ``local`` adapter ignores it). The item/section
    # caps and character floor bound deck density; ``quiz_dedup_threshold`` is the
    # cosine-similarity ceiling above which a candidate is a near-duplicate; the batch
    # timeout/poll-interval bound the Anthropic Message Batches polling loop.
    # ``quiz_max_suggestions`` caps the interactive per-quote card suggestions (RFC-004
    # Cycle D) and is deliberately separate from ``quiz_max_items_per_section`` so
    # tuning the foreground popover never moves whole-deck density.
    # ``quiz_max_card_chars`` bounds the question/answer text a student may accept or
    # edit onto one card. ``quiz_note_excerpt_chars`` bounds the note-body excerpt
    # snapshotted onto a promoted ``note`` card (its provenance line and standalone
    # citation) — a note is the whole source, so the excerpt is a readable prefix.
    quiz_model: str = "claude-haiku-4-5"
    quiz_max_items_per_section: int = 6
    quiz_max_suggestions: int = 3
    quiz_max_card_chars: int = 2000
    quiz_note_excerpt_chars: int = 2000
    # ``quiz_note_match_threshold`` is the cosine floor for pairing a live note card
    # with a freshly generated suggestion during regenerate-and-match (NL-10). It is
    # deliberately looser than ``quiz_dedup_threshold`` (0.90): that ceiling rejects
    # near-duplicates, whereas matching an *edited* note's reworded card to its prior
    # version must tolerate more drift.
    quiz_note_match_threshold: float = 0.80
    quiz_min_section_chars: int = 200
    quiz_dedup_threshold: float = 0.90
    quiz_batch_timeout_s: int = 3600
    quiz_batch_poll_interval_s: int = 30

    # Active recall — FSRS scheduling (RFC-002 Cycle E). ``fsrs_desired_retention`` is
    # the FSRS-6 target recall probability; ``fsrs_fuzzing`` spreads due dates to avoid
    # review pile-ups (disabled in tests for deterministic interval assertions).
    fsrs_desired_retention: float = 0.9
    fsrs_fuzzing: bool = True

    # Notes & second-brain (RFC-003 Cycle E; ADR-0026). ``notes_max_body_chars`` caps a
    # note's Markdown body length, enforced by the note use cases before any write.
    notes_max_body_chars: int = 100000
    # Deterministic truncation applied to a note body before it is embedded, so an
    # oversized note never breaches the embedding provider's per-input limit (~8191
    # tokens for OpenAI); ~4 chars/token keeps this comfortably under it. The default
    # local adapter has no limit, so truncation is a no-op there.
    notes_embedding_max_chars: int = 32000

    # App instrumentation (RFC-006 Cycle A). ``dev_instrument_enabled`` gates the
    # dev-only surface that *exposes* recorded timings, never the recording itself:
    # collection is a bounded in-memory append, and gating it would leave a running
    # process undiagnosable without a restart that discards the evidence being
    # chased (AD-173). It defaults false and is absent from the production compose.
    # ``instrument_capacity`` is the sample count kept per process (requests and
    # slow-query entries are bounded separately by it) and
    # ``slow_query_statement_chars`` caps the captured statement text; both mirror
    # the recorder's process defaults in ``app.core.instrumentation``. A statement
    # counts as slow at or above ``slow_query_ms`` — set to zero or below every
    # statement qualifies, deliberately, so the path is exercisable without
    # sleeping (AD-175).
    dev_instrument_enabled: bool = False
    instrument_capacity: int = 500
    slow_query_ms: int = 200
    slow_query_statement_chars: int = 2000

    # The eval-results dashboard (RFC-005 Cycle D). ``dev_eval_dashboard_enabled``
    # gates a second, independent dev-only surface: the nightly eval JSONL has
    # accumulated since v2 with nothing rendering it. It carries its own switch
    # rather than riding the instrument's so either surface can be turned on
    # alone, and — like the instrument — a production process refuses it whatever
    # the environment hands in (AD-243). ``eval_results_dir`` unset means the
    # judge's own ``RESULTS_DIR``, which on a default checkout holds only the
    # committed golden files; point it at a checkout of the ``eval-results``
    # branch to render the full nightly history without putting git in the
    # request path (AD-239). The reader walks it recursively, so either layout
    # reads the same.
    dev_eval_dashboard_enabled: bool = False
    eval_results_dir: Path | None = None

    # The page unit (RFC-006 Cycle B). An EPUB reflows, so a book has no intrinsic
    # page; ``words_per_page`` defines one. Pages are derived from the word counts
    # already stored per corpus section, so every book that has ever been ingested
    # gains pages retroactively — no corpus column, no re-processing. This is the
    # single definition of the quantum: the reader receives it on the chapter
    # response instead of hard-coding it, and the per-day pages figure on the study
    # window resolves to the same value.
    words_per_page: int = 275

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Keep the default source precedence, remembering what the env file holds.

        The env-file source is the only place that knows which file this
        instantiation actually read, so the names it carries are captured here for
        the retired-knob warning below. ``extra`` is ``ignore``, which means a
        retired name in that file is dropped before any field sees it — capturing
        the raw variable names is what keeps it visible.
        """
        env_file_vars = getattr(dotenv_settings, "env_vars", {})
        _env_file_vars.set(frozenset(name.upper() for name in env_file_vars))
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    @model_validator(mode="after")
    def _warn_about_retired_knobs(self) -> Settings:
        """Say once, at startup, that a retired variable no longer does anything.

        The failure this prevents is silent: a deployment that raised
        ``LEARNY_TEACHING_HISTORY_TURNS`` to 12 still validates, still boots, and
        quietly serves the new default instead. Its startup *succeeding* is the point
        — nothing should break because a stale variable lingers — and it is also
        exactly what makes a dead tuning look like a live one. A comment in this file
        is not reachable by the person running the deploy.

        Read from the variable names rather than from the declared fields: the fields
        are gone, and a check over ``model_fields_set`` would quietly stop firing at
        the moment the variable became most misleading. Both places settings are read
        from count — the process environment (Compose and the VPS unit inject them
        there) and the ``.env`` file, which pydantic-settings loads separately and
        which ``os.environ`` cannot see. A knob set anywhere the value *would* have
        been read from is a knob the operator believes in.

        The old value is deliberately *not* inherited into the new setting: that would
        re-couple the per-surface knobs the unified settings separated, for the sake
        of a tuning this deployment never made. Naming the variable and the value now
        in force lets an operator re-tune deliberately.
        """
        env_file_vars = _env_file_vars.get()
        for env_var, successor in _RETIRED_KNOBS.items():
            if env_var in os.environ or env_var in env_file_vars:
                logger.warning(
                    "%s is retired and no longer read; %s=%s is in force. "
                    "Set LEARNY_%s to change it.",
                    env_var,
                    successor,
                    getattr(self, successor),
                    successor.upper(),
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance loaded from the environment."""
    return Settings()
