"""The golden-capture operator runner, proven offline (``capture_local_golden``).

Two facts, three proofs:

- Invoked without ``--base-url`` or ``--model`` the runner refuses with exit
  ``2`` before any network attempt or database write — the seams that would
  touch either are replaced with tripwires first;
- the provenance stamp is this checkout's HEAD, resolved at the repository root
  (the directory holding ``evals/``) — never one directory above it, which would
  name an outer repository's HEAD when the checkout sits inside another;
- the same runner an operator points at Ollama records one JSONL line per
  golden case under ``evals/local/`` — proven end-to-end against an
  in-process OpenAI-compatible fake server on a loopback ephemeral port with
  deterministic scripted responses: real ingestion of both golden books into
  the test database, the real hybrid retrieval, generation over real HTTP.
"""

from __future__ import annotations

import json
import subprocess
import threading
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import TracebackType

import pytest
from sqlalchemy import Connection

from tests.conftest import requires_db

# The scripted reply cites evidence document [^1], so every case resolves its
# marker against retrieved evidence: found with a valid citation.
_SCRIPTED_REPLY = "Scripted grounded reply [^1]."
_SCRIPTED_MODEL = "scripted-local-model"

_DOOR4_FIELDS = {
    "case_id",
    "language",
    "question",
    "expected_status",
    "found",
    "cited_chunk_ids",
    "citation_valid",
    "generation_model",
    "base_url",
    "ts",
    "git_sha",
    "answer_text",
}

# 12 English cases.yaml cases + 3 Portuguese inflection cases + the Portuguese
# unsupported question — the full golden set the runner must answer.
_EXPECTED_CASES = 16


class _FakeCompletionHandler(BaseHTTPRequestHandler):
    """An OpenAI-compatible chat-completions endpoint with one scripted reply."""

    def do_POST(self) -> None:  # noqa: N802 — http.server's verb naming
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = json.dumps(
            {
                "id": "chatcmpl-scripted",
                "object": "chat.completion",
                "created": 0,
                "model": _SCRIPTED_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": _SCRIPTED_REPLY},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence per-request logging — the test's own assertions are the record."""


class _ConnectionUow(AbstractContextManager):
    """Serves the runner's unit-of-work seam with the test's transaction."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def __enter__(self) -> Connection:
        return self._conn

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return False


def test_missing_args_exit_two_before_network_or_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # noqa: ANN001 — tmp_path
    # AC 20: either flag missing alone is a usage refusal, and the refusal
    # happens in argument parsing — before the UoW is opened, the fixtures are
    # imported, or anything is written.
    import app.cli.capture_local_golden as capture

    def _tripwire() -> AbstractContextManager:
        raise AssertionError("usage refusal reached the database unit of work")

    monkeypatch.setattr(capture, "_uow", _tripwire)
    monkeypatch.setattr(capture, "_output_dir", tmp_path)

    with pytest.raises(SystemExit) as missing_model:
        capture.main(["--base-url", "http://localhost:11434/v1"])
    assert missing_model.value.code == 2

    with pytest.raises(SystemExit) as missing_base_url:
        capture.main(["--model", "qwen3:8b"])
    assert missing_base_url.value.code == 2

    with pytest.raises(SystemExit) as missing_both:
        capture.main([])
    assert missing_both.value.code == 2

    assert not tmp_path.exists() or not any(tmp_path.iterdir())


def test_git_sha_stamps_this_checkout_head() -> None:
    # The provenance stamp is this checkout's HEAD — resolved at the repository
    # root (the directory holding evals/), even when the checkout itself sits
    # inside another repository, where a resolution above the root would name
    # the outer repository's HEAD.
    import app.cli.capture_local_golden as capture

    repo_root = Path(__file__).resolve().parents[2]
    try:
        expected = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        expected = "unknown"
    assert capture._git_sha() == expected


def test_git_sha_falls_back_to_unknown_outside_a_repo(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001 — tmp_path
    import app.cli.capture_local_golden as capture

    monkeypatch.setattr(capture, "_output_dir", tmp_path / "evals" / "local")
    assert capture._git_sha() == "unknown"


@requires_db
def test_records_one_line_per_case(
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # noqa: ANN001 — fixtures
    # AC 19/21: the same runner an operator points at Ollama, driven against an
    # in-process scripted runtime — one JSONL line per golden case, every line
    # naming the --model argument, all door-4 fields present.
    import app.cli.capture_local_golden as capture

    server = HTTPServer(("127.0.0.1", 0), _FakeCompletionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setattr(capture, "_uow", lambda: _ConnectionUow(db_conn))
    monkeypatch.setattr(capture, "_output_dir", tmp_path)
    try:
        exit_code = capture.main(["--base-url", base_url, "--model", _SCRIPTED_MODEL])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert exit_code == 0
    captures = list(tmp_path.glob("*.jsonl"))
    assert len(captures) == 1, "one capture file per run"
    records = [json.loads(line) for line in captures[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == _EXPECTED_CASES
    assert all(record["generation_model"] == _SCRIPTED_MODEL for record in records)
    assert all(_DOOR4_FIELDS <= set(record) for record in records)
    assert all(record["base_url"] == base_url for record in records)

    by_language = {"en": 0, "pt": 0}
    for record in records:
        by_language[record["language"]] += 1
    assert by_language == {"en": 12, "pt": 4}

    # The scripted reply cites [^1]: every case is found with a valid citation
    # resolving to retrieved evidence, and the raw answer rides on the line.
    assert all(record["found"] is True for record in records)
    assert all(record["citation_valid"] is True for record in records)
    assert all(record["cited_chunk_ids"] for record in records)
    assert all(record["answer_text"] == _SCRIPTED_REPLY for record in records)
    assert all(
        record["expected_status"] in {"answered", "not_found_in_source"} for record in records
    )
