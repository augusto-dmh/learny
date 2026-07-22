"""Silver case loader/validation (DEEP-01/04, DEEP-17 load leg).

Derived from the spec: a well-formed ``cases.yaml`` loads into typed cases, and
every malformed shape aborts on load with :class:`SilverCaseError` naming the
offending case id and field — so a bad local file is fixed before any resolution
or provider call. Uses tmp fixtures only; no dependence on real local data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.eval.silver import (
    SilverCase,
    SilverCaseError,
    advisory_case_count,
    load_silver_cases,
)


def _valid_case(**overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "case_id": "pt-lideranca-servidora",
        "question": "O que caracteriza a lideranca servidora?",
        "source_checksum": "a" * 64,
        "expected_anchors": ["chapter1.xhtml#s1"],
        "expected_snippet": "A lideranca servidora coloca a equipe primeiro.",
        "language": "portuguese",
    }
    case.update(overrides)
    return case


def _write(tmp_path: Path, cases: list[dict[str, Any]]) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump({"cases": cases}), encoding="utf-8")
    return path


# --- Happy path ----------------------------------------------------------------


def test_valid_file_loads_into_typed_cases(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _valid_case(),
            _valid_case(
                case_id="en-trust-pyramid",
                question="What sits at the base of the trust pyramid?",
                source_checksum="b" * 64,
                expected_anchors=["ch2.xhtml#a", "ch2.xhtml#b"],
                expected_snippet="Trust is the foundation of a functioning team.",
                language="english",
            ),
        ],
    )

    cases = load_silver_cases(path)

    assert [c.case_id for c in cases] == ["pt-lideranca-servidora", "en-trust-pyramid"]
    assert all(isinstance(c, SilverCase) for c in cases)
    # Anchors are a tuple (hashable, order preserved) and languages span the set.
    assert cases[0].expected_anchors == ("chapter1.xhtml#s1",)
    assert cases[1].expected_anchors == ("ch2.xhtml#a", "ch2.xhtml#b")
    assert {c.language for c in cases} == {"portuguese", "english"}


# --- Malformed shapes each name case + field ----------------------------------


def _assert_raises_on(tmp_path: Path, *, field: str, case: dict[str, Any]) -> None:
    with pytest.raises(SilverCaseError) as exc:
        load_silver_cases(_write(tmp_path, [case]))
    assert exc.value.field == field
    # The message carries both the case id and the field for a one-line fix.
    assert exc.value.case_id in str(exc.value)
    assert field in str(exc.value)


def test_missing_question_raises(tmp_path: Path) -> None:
    case = _valid_case()
    del case["question"]
    _assert_raises_on(tmp_path, field="question", case=case)


def test_bad_checksum_raises(tmp_path: Path) -> None:
    _assert_raises_on(
        tmp_path, field="source_checksum", case=_valid_case(source_checksum="not-a-hash")
    )


def test_uppercase_checksum_raises(tmp_path: Path) -> None:
    # sha256 hex is lowercase; an uppercase 64-char value is rejected, not coerced.
    _assert_raises_on(
        tmp_path, field="source_checksum", case=_valid_case(source_checksum="A" * 64)
    )


def test_empty_anchors_raises(tmp_path: Path) -> None:
    _assert_raises_on(tmp_path, field="expected_anchors", case=_valid_case(expected_anchors=[]))


def test_anchor_blank_entry_raises(tmp_path: Path) -> None:
    _assert_raises_on(
        tmp_path, field="expected_anchors", case=_valid_case(expected_anchors=["ok", "  "])
    )


def test_missing_snippet_raises(tmp_path: Path) -> None:
    case = _valid_case()
    del case["expected_snippet"]
    _assert_raises_on(tmp_path, field="expected_snippet", case=case)


def test_unknown_language_raises(tmp_path: Path) -> None:
    _assert_raises_on(tmp_path, field="language", case=_valid_case(language="french"))


def test_missing_case_id_raises(tmp_path: Path) -> None:
    case = _valid_case()
    del case["case_id"]
    with pytest.raises(SilverCaseError) as exc:
        load_silver_cases(_write(tmp_path, [case]))
    assert exc.value.field == "case_id"


def test_duplicate_case_id_raises(tmp_path: Path) -> None:
    with pytest.raises(SilverCaseError) as exc:
        load_silver_cases(_write(tmp_path, [_valid_case(), _valid_case()]))
    assert exc.value.field == "case_id"
    assert exc.value.case_id == "pt-lideranca-servidora"


# --- Structural errors ---------------------------------------------------------


def test_missing_cases_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump({"items": []}), encoding="utf-8")
    with pytest.raises(SilverCaseError) as exc:
        load_silver_cases(path)
    assert exc.value.field == "cases"


def test_empty_cases_list_raises(tmp_path: Path) -> None:
    with pytest.raises(SilverCaseError) as exc:
        load_silver_cases(_write(tmp_path, []))
    assert exc.value.field == "cases"


# --- Advisory bounds (not a schema gate) --------------------------------------


def test_advisory_count_flags_too_few_and_too_many(tmp_path: Path) -> None:
    few = [SilverCase("c", "q", "a" * 64, ("x",), "s", "english")] * 3
    plenty = few * 5  # 15
    many = few * 7  # 21

    assert advisory_case_count(few) is not None
    assert "minimum" in advisory_case_count(few)
    assert advisory_case_count(plenty) is None
    assert advisory_case_count(many) is not None
    assert "maximum" in advisory_case_count(many)
