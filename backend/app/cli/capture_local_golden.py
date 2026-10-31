"""Capture golden results from a local OpenAI-compatible runtime (``capture_local_golden``).

The operator command behind ``docs/ops/local-models.md``'s golden-results
procedure: point it at a local runtime (Ollama ``http://localhost:11434/v1``,
LM Studio ``http://localhost:1234/v1``) and it answers every golden case — the
12 English ``cases.yaml`` cases plus the 4 Portuguese golden-book cases —
through the real composition (real ingestion of the two golden books into the
configured database, the settings-selected embedding adapter, the real hybrid
retrieval service, and an ``OpenAICompatibleGenerationAdapter`` at
``--base-url`` naming ``--model``). One JSONL line per case lands under
``evals/local/`` with the door-4 fields plus the raw answer text, and a summary
is printed on stdout. Nothing is scored or judged — the capture records
deterministic facts; judging faithfulness is a separate judge-owned study.

Exit codes: ``0`` when the capture is recorded; ``2`` on a usage refusal
(missing ``--base-url`` or ``--model``), raised by argument parsing before any
network attempt or database write. The capture never reads
``LEARNY_OPENAI_API_KEY``: every request carries the fixed placeholder key, so
the environment's hosted key is never handed to the runtime ``--base-url`` names.

The golden books and the case lists are the repo's canonical fixtures, owned by
the test suite (``tests/golden_corpus*``, ``tests/eval/cases.yaml``,
``tests/golden_expected``) — the same books and cases the golden checks assert
against. This runner is a repo tool run from a checkout (the documented
procedure runs it from ``backend/``), so it imports those fixtures directly:
one definition serves the checks and the capture, and a capture can never
drift from what the golden checks measure. The imports are lazy so the
usage-refusal path stays free of them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Connection

from app.application.grounding import ground
from app.application.identity import AuthorizeOwnership
from app.application.retrieval import RetrieveEvidence
from app.core.config import Settings, get_settings
from app.domain.entities import MODE_ANSWER, IngestionJob, Source, User
from app.infrastructure.answering.openai_compat import OpenAICompatibleGenerationAdapter
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyReadingPositionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.ingestion.epub import EbooklibEpubParser
from app.infrastructure.ingestion.images import PillowImageEncoder
from app.infrastructure.ingestion.markup import Bs4MarkupConverter

#: The unit of work the capture runs in (tests inject the transactional test
#: connection). Production default: one engine transaction, committed on success.
_uow: Callable[[], AbstractContextManager[Connection]] = get_engine().begin  # type: ignore[assignment]

#: Where the JSONL capture lands: ``evals/local/`` in the repo root — local
#: runtime captures only, never ``evals/results/`` (the judge-owned dashboard
#: input). Tests point this at a temp directory.
_output_dir: Path = Path(__file__).resolve().parents[3] / "evals" / "local"

# The generation budget a local capture gets. Local runtimes have no token bill;
# 2048 is the ops doc's recommended start for the documented profile.
_CAPTURE_MAX_TOKENS = 2048

# The API key sent on every capture request — always this placeholder, never the
# environment's ``LEARNY_OPENAI_API_KEY``: the documented targets are keyless
# local runtimes that ignore the value entirely, so forwarding the real hosted
# key would only leak it to whatever ``--base-url`` names (the ops runbook
# records this). The OpenAI SDK still requires a non-empty string.
_KEY_PLACEHOLDER = "local-capture"


@dataclass(frozen=True)
class _CaptureCase:
    """One golden case the capture answers: identity, language, expectation."""

    case_id: str
    language: str
    question: str
    expected_status: str


@dataclass(frozen=True)
class _GoldenBook:
    """One golden book: its EPUB bytes and the cases asked against it."""

    name: str
    epub: bytes
    cases: tuple[_CaptureCase, ...]


class _CaptureStorage:
    """In-memory object storage serving the capture's own golden EPUBs.

    The capture ingests books it holds in memory — there is no upload step —
    so the storage port is served by a dict keyed by object key. The books ride
    the same real ``BuildCorpus`` read path (``get_object``) as an uploaded
    source; only the byte source differs, and it is the capture's own data, not
    a test-only branch.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        self._objects[key] = data

    def get_object(self, key: str) -> bytes:
        return self._objects[key]

    def delete_object(self, key: str) -> None:
        self._objects.pop(key, None)


def _golden_books() -> tuple[_GoldenBook, _GoldenBook]:
    """The two canonical golden books with their case lists (lazy imports)."""
    from tests.eval.harness import load_cases
    from tests.golden_corpus import golden_book
    from tests.golden_corpus_pt import portuguese_golden_book
    from tests.golden_expected import PORTUGUESE_CASES, PORTUGUESE_UNSUPPORTED_QUESTION

    english = _GoldenBook(
        name="golden-book",
        epub=golden_book(),
        cases=tuple(
            _CaptureCase(
                case_id=case.case_id,
                language="en",
                question=case.question,
                expected_status=case.expected_status,
            )
            for case in load_cases()
        ),
    )
    portuguese = _GoldenBook(
        name="portuguese-golden-book",
        epub=portuguese_golden_book(),
        cases=(
            *tuple(
                _CaptureCase(
                    case_id=f"portuguese-case-{number}",
                    language="pt",
                    question=case.question,
                    expected_status="answered",
                )
                for number, case in enumerate(PORTUGUESE_CASES, start=1)
            ),
            _CaptureCase(
                case_id="portuguese-not-found",
                language="pt",
                question=PORTUGUESE_UNSUPPORTED_QUESTION,
                expected_status="not_found_in_source",
            ),
        ),
    )
    return english, portuguese


def _git_sha() -> str:
    """The short commit sha stamped on every line (``unknown`` outside a repo).

    Resolved at the repository root — the directory that holds ``evals/`` — so
    the stamp is this checkout's HEAD even when the checkout itself sits inside
    another repository (a worktree under a parent clone, for instance); running
    git above the repo root would name the outer repository's HEAD or nothing.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_output_dir.parents[1],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _seed_book(conn: Connection, *, book: _GoldenBook, settings: Settings) -> tuple[User, Source]:
    """Ingest one golden book into the database and embed every chunk.

    The real ingestion composition (real parser, markup converter, chunker,
    corpus repository, events) and the real embedding write path (the
    settings-selected adapter stamps every vector with its identity) — the same
    corpus the golden checks build, under a throwaway owner.
    """
    from app.application.corpus import BuildCorpus

    now = datetime.now(UTC)
    storage = _CaptureStorage()
    object_key = f"capture/{book.name}.epub"
    storage.put_object(object_key, book.epub, content_type="application/epub+zip")
    user = User(id=uuid4(), email=f"capture-{uuid4()}@example.com", created_at=now)
    SqlAlchemyUserRepository(conn).add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title=book.name,
        filename=f"{book.name}.epub",
        content_type="application/epub+zip",
        byte_size=len(book.epub),
        checksum="0" * 64,
        object_key=object_key,
        status="ready",
        created_at=now,
        updated_at=now,
    )
    SqlAlchemySourceRepository(conn).add(source)
    job = SqlAlchemyIngestionJobRepository(conn).add(
        IngestionJob(
            id=uuid4(),
            source_id=source.id,
            status="succeeded",
            attempts=1,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    BuildCorpus(
        storage=storage,
        parser=EbooklibEpubParser(max_uncompressed_bytes=settings.epub_max_uncompressed_bytes),
        markup=Bs4MarkupConverter(),
        corpus=SqlAlchemyCorpusRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        clock=SystemClock(),
        ids=uuid4,
        chunk_max_chars=settings.chunk_max_chars,
        encoder=PillowImageEncoder(),
    )(source=source, job=job)

    index = SqlAlchemyEmbeddingIndexRepository(conn)
    embeddings = build_embedding_adapter(settings)
    chunks = index.chunks_for_source(source.id)
    vectors = embeddings.embed_documents([chunk.text for chunk in chunks])
    index.set_embeddings(
        list(zip((chunk.id for chunk in chunks), vectors, strict=True)),
        model=embeddings.model,
    )
    return user, source


def _sanitize_model(model: str) -> str:
    """A filename-safe form of the model id (``qwen3:8b`` → ``qwen3-8b``)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")


def _capture(base_url: str, model: str) -> Path:
    """Run every golden case and record one JSONL line per case; return the path."""
    # One resolution per run: the provenance stamp is a property of the checkout,
    # not of a case — the same sha rides every line and the filename.
    git_sha = _git_sha()
    settings = get_settings()
    embeddings = build_embedding_adapter(settings)
    generation = OpenAICompatibleGenerationAdapter(
        api_key=_KEY_PLACEHOLDER,
        model=model,
        max_tokens=_CAPTURE_MAX_TOKENS,
        base_url=base_url,
    )
    records: list[dict[str, object]] = []
    with _uow() as conn:
        retrieve_evidence = RetrieveEvidence(
            sources=SqlAlchemySourceRepository(conn),
            retrieval=SqlAlchemyRetrievalRepository(conn),
            embeddings=embeddings,
            positions=SqlAlchemyReadingPositionRepository(conn),
            authorize=AuthorizeOwnership(),
            semantic_limit=settings.retrieval_semantic_limit,
            lexical_limit=settings.retrieval_lexical_limit,
            rrf_k=settings.retrieval_rrf_k,
            ef_search=settings.hnsw_ef_search,
            default_top_k=settings.retrieval_top_k,
        )
        for book in _golden_books():
            user, source = _seed_book(conn, book=book, settings=settings)
            for case in book.cases:
                evidence = retrieve_evidence(user=user, source_id=source.id, query=case.question)
                generated = generation.generate(
                    message=case.question, mode=MODE_ANSWER, evidence=evidence
                )
                grounded = ground(generated, evidence)
                cited = set(generated.cited_chunk_ids)
                evidence_ids = {item.chunk_id for item in evidence}
                citation_valid = (not generated.found and not cited) or (
                    generated.found and bool(cited) and cited <= evidence_ids
                )
                records.append(
                    {
                        "case_id": case.case_id,
                        "language": case.language,
                        "question": case.question,
                        "expected_status": case.expected_status,
                        "found": grounded is not None,
                        "cited_chunk_ids": (
                            [str(item.chunk_id) for item in grounded[1]] if grounded else []
                        ),
                        "citation_valid": citation_valid,
                        "generation_model": generated.model,
                        "base_url": base_url,
                        "ts": datetime.now(UTC).isoformat(),
                        "git_sha": git_sha,
                        "answer_text": generated.text,
                    }
                )
    _output_dir.mkdir(parents=True, exist_ok=True)
    path = _output_dir / (
        f"{datetime.now(UTC).strftime('%Y-%m-%d')}-{git_sha}-{_sanitize_model(model)}.jsonl"
    )
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    found = sum(1 for record in records if record["found"])
    print(f"recorded {len(records)} golden cases ({found} found) -> {path}")
    print(f"generation: {model} @ {base_url}; embeddings: {embeddings.model}")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: parse, refuse usage with exit ``2``, or capture."""
    parser = argparse.ArgumentParser(
        prog="capture_local_golden",
        description=(
            "Answer every golden case through a local OpenAI-compatible runtime "
            "and record one JSONL line per case under evals/local/."
        ),
    )
    parser.add_argument(
        "--base-url", required=True, help="the runtime's OpenAI-compatible base URL"
    )
    parser.add_argument("--model", required=True, help="the model id the runtime serves")
    args = parser.parse_args(argv)
    _capture(args.base_url, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
