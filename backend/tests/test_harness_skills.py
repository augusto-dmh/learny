"""Sensors for the delivery harness's skills and docs (PR A's skill claims, PR B's loop).

PR A pruned the skill tree and rewired the attribution contract; PR B vendored the lean
spec skill into ``.claude/skills/tlc-spec-lean/`` and put the ship cycle, the review
lanes and the publishing conventions on it. These tests pin both at HEAD so a fresh
clone keeps the promises: the vendored tree is complete and carries its recorded
deviations, the ship cycle detects lean artifact states and picks a lane by rule, review
reads lean artifacts with a legacy fallback, and every proof in the harness feature's
``checks.md`` runs wherever the repo is cloned.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEAN = _REPO_ROOT / ".claude" / "skills" / "tlc-spec-lean"
_SHIP_CYCLE = (_REPO_ROOT / ".claude" / "skills" / "learny-ship-cycle" / "SKILL.md").read_text()
_FINALIZE = (_REPO_ROOT / ".claude" / "skills" / "learny-finalize" / "SKILL.md").read_text()
_PR_REVIEW = (_REPO_ROOT / ".claude" / "skills" / "pr-review" / "SKILL.md").read_text()
_SKILLS_MD = (_REPO_ROOT / "SKILLS.md").read_text()
_SKILLS_README = (_REPO_ROOT / ".claude" / "skills" / "README.md").read_text()
_CHECKS_MD = (_REPO_ROOT / ".specs" / "features" / "harness-reset" / "checks.md").read_text()

_REMOVED_SKILLS = (
    "tlc-spec-driven",
    "redis-observability",
    "redis-security",
    "domain-analysis",
    "skill-architect",
    "grilling",
    "grill-me",
    "create-technical-design-doc",
)

_KEPT_SKILLS = (
    "learny-ship-cycle",
    "learny-finalize",
    "pr-review",
    "fastapi",
    "pgvector-hybrid-search",
    "celery-workers",
    "epub-ingestion",
    "create-adr",
    "create-rfc",
    "uv",
    "ruff",
    "vercel-composition-patterns",
    "vercel-react-best-practices",
    "web-design-guidelines",
    "modular-design-principles",
    "redis-core",
)

_MODEL_ROWS = (
    "| Plan and door gate (main thread) | Fable or Opus |",
    "| Build | Opus |",
    "| Verifier | Opus, never the cheapest tier |",
    "| Review lanes | Sonnet for mechanical lanes, "
    "Opus for correctness, security and architecture |",
    "| Sub-agents | Never Fable |",
)

_VENDORED_SCRIPTS = (
    "check_commit",
    "check_proofs",
    "lean_config",
    "lessons",
    "mutate",
    "runners",
    "selftest",
    "validate_checks",
    "validate_plan",
    "validate_verification",
)


def _between(text: str, start: str, end: str) -> str:
    """The text after `start` up to the next `end`, so a sensor reads one section only."""
    return text.split(start, 1)[1].split(end, 1)[0]


def _load_script(name: str, path: Path):
    """Load a stdlib gate script as a module, the way its own tests drive it."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_REPO_CHECKER = _load_script(
    "check_commits", _REPO_ROOT / "backend" / "scripts" / "check_commits.py"
)
_VENDORED_GATE = _load_script("vendored_check_commit", _LEAN / "scripts" / "check_commit.py")

# The archived decision log is frozen content: pin it by digest so the equality runs in
# every checkout, including the depth-1 clone CI merges from, where git history cannot
# supply the pre-archive file.
_ARCHIVE_SHA256 = "c6965e0fbd9eba0a84f79378ac602cc6ab7e80ae2a6763ae1db1f9fafa9d310b"


# --- S5: the harness loads only what it uses (PR A claims, re-proven portably) ---


def test_the_state_archive_is_intact_and_the_live_state_is_lean() -> None:
    archive = _REPO_ROOT / ".specs" / "project" / "archive" / "STATE-v1-v7.md"
    assert archive.is_file(), "the archived decision log is missing"
    # The archive must stay byte-identical to the state file it replaced. The digest is
    # over the stored (LF) bytes, so a Windows checkout normalizes before hashing.
    digest = hashlib.sha256(archive.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert digest == _ARCHIVE_SHA256, "the archive no longer matches the original"
    live = (_REPO_ROOT / ".specs" / "project" / "STATE.md").read_text()
    sections = [line[3:].strip() for line in live.splitlines() if line.startswith("## ")]
    assert sections == ["Handoff", "Open decisions"], sections


def test_the_lessons_files_gone_stay_gone() -> None:
    for path in (".specs/LESSONS.md", ".specs/lessons.json"):
        assert not (_REPO_ROOT / path).exists(), f"{path} came back"


def test_the_removed_skills_absent_from_the_skills_tree() -> None:
    present = {p.name for p in (_REPO_ROOT / ".claude" / "skills").iterdir() if p.is_dir()}
    clash = present & set(_REMOVED_SKILLS)
    assert not clash, sorted(clash)


def test_the_kept_skills_present_with_a_skill_md() -> None:
    for name in _KEPT_SKILLS:
        assert (_REPO_ROOT / ".claude" / "skills" / name / "SKILL.md").is_file(), name


def test_the_removed_skills_unlisted_in_the_skill_indexes() -> None:
    indexed = _SKILLS_MD + _SKILLS_README + (_REPO_ROOT / "skills-lock.json").read_text()
    lock = _REPO_ROOT / ".agents" / ".skill-lock.json"
    if lock.is_file():
        indexed += lock.read_text()
    for name in _REMOVED_SKILLS:
        assert name not in indexed, f"the removed skill {name} is still listed somewhere"


def test_the_ship_cycle_carries_the_synthesis_model_table() -> None:
    for row in _MODEL_ROWS:
        assert row in _SHIP_CYCLE, f"model row drifted: {row}"
    assert "never Sonnet" not in _SHIP_CYCLE
    assert "Haiku" not in _SHIP_CYCLE


def test_the_attribution_setting_pins_the_contract() -> None:
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text())
    assert settings.get("attribution") == {"commit": "Assisted-by: Claude Code", "pr": ""}
    assert "includeCoAuthoredBy" not in settings


def test_the_finalize_trailer_rule_requires_the_override() -> None:
    assert "Assisted-by: Claude Code" in _FINALIZE
    assert "override of `tlc-spec-lean`'s rule" in _FINALIZE
    assert "Co-authored-by" in _FINALIZE and "Made-with" in _FINALIZE
    assert "PR titles, PR bodies and PR comments carry no attribution" in _FINALIZE
    assert "Never add authorship or tooling attribution to commits" not in _FINALIZE


def test_the_roadmap_harness_rows_cover_both_prs() -> None:
    roadmap = (_REPO_ROOT / ".specs" / "project" / "ROADMAP.md").read_text()
    section = roadmap.split("## Harness", 1)[1]
    # Both rows only: the PR B row's status is set by the wrap commit, so this proof
    # must read green before and after it.
    assert "`harness-reset` PR A" in section
    assert "`harness-reset` PR B" in section


def test_the_hygiene_verifier_requires_db_and_infra() -> None:
    assert "LEARNY_REQUIRE_DB=1" in _SHIP_CYCLE
    assert "make infra" in _SHIP_CYCLE


# --- S8: the lean spec skill is vendored with its deviations ---


def test_the_vendored_tree_is_complete() -> None:
    files = [
        _LEAN / "SKILL.md",
        *(
            _LEAN / "references" / f"{name}.md"
            for name in ("build", "checks", "memory", "plan", "verify", "verify-screens")
        ),
        *(_LEAN / "scripts" / f"{name}.py" for name in _VENDORED_SCRIPTS),
        *(
            _LEAN / "scripts" / "fixtures" / f"{name}.md"
            for name in ("checks", "plan", "proofs", "verification")
        ),
    ]
    missing = [str(p.relative_to(_REPO_ROOT)) for p in files if not p.is_file()]
    assert not missing, f"vendored tree incomplete: {missing}"
    assert "name: tlc-spec-lean" in (_LEAN / "SKILL.md").read_text()


def test_the_vendored_runners_carry_the_windows_launcher_fix() -> None:
    # The vendored copy must keep the source's Windows fix: `.cmd`/`.bat` shims
    # (`npx`, `pnpm`) cannot be CreateProcess'd directly, so the runner resolves
    # through PATH/PATHEXT and goes through `cmd /c`.
    runners = (_LEAN / "scripts" / "runners.py").read_text()
    assert "_resolve(" in runners and "shutil.which" in runners, (
        "the vendored runners lost the Windows launcher fix the README records"
    )
    assert "--testTimeout=120000" in runners, "grouped vitest runs keep the long timeouts"


def test_the_vendored_deviations_are_declared() -> None:
    skill = (_LEAN / "SKILL.md").read_text()
    section = _between(skill, "## Learny deviations", "## Configuration")
    assert "per-batch" in section and "Verifier" in section, "the batch-scoped Verifier deviation"
    assert "D2" in section and "D3" in section, "the owner decisions named"
    assert "Assisted-by: Claude Code" in section, "the trailer deviation"
    assert "no-agent-trailer" in section, "the overridden lean rule named"
    assert "backend/scripts/check_commits.py" in section, "the repo checker named as the authority"
    assert "revert" in section, "the gate's type list matches the repo's 11 types"
    assert "trailer" in section and "kebab-case" in section, (
        "the rules the local gate does not enforce are named"
    )
    assert ".specs/project/STATE.md" in section, "the decisions location deviation recorded"
    assert "waive" in section, "the plan-gate decisions lookup waiver recorded"


def test_the_vendored_build_override_requires_the_trailer() -> None:
    build = (_LEAN / "references" / "build.md").read_text()
    assert "Assisted-by: Claude Code" in build
    assert "every commit" in build
    assert "exception" in build and "no-agent-trailer rule" in build


def test_the_vendored_commit_gate_types_match_the_repo_checker() -> None:
    assert set(_VENDORED_GATE.TYPES) == set(_REPO_CHECKER.TYPES), (
        "the vendored gate's type list drifted from the authoritative checker"
    )


@pytest.mark.parametrize("commit_type", sorted(_REPO_CHECKER.TYPES))
def test_the_vendored_commit_gate_accepts_every_repo_type(commit_type: str) -> None:
    gate = _LEAN / "scripts" / "check_commit.py"
    good = subprocess.run(
        [sys.executable, str(gate), "--message", f"{commit_type}(x): add validation"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr


def test_the_vendored_commit_gate_leaves_the_trailer_to_ci() -> None:
    # The recorded deviation: the local gate is a fast per-commit check and does not
    # enforce the attribution rules; CI's commits job does. Pin the gap so the
    # documentation cannot drift into claiming the gate enforces them.
    trailerless = "feat(x): add validation\n"
    assert _VENDORED_GATE.check(trailerless)[0] == [], (
        "the gate passes a trailer-less message - that is the recorded gap"
    )
    assert _REPO_CHECKER.check_message(trailerless), "the repo checker rejects the same message"


def test_the_vendored_commit_gate_rejects_a_disallowed_type() -> None:
    gate = _LEAN / "scripts" / "check_commit.py"
    bad = subprocess.run(
        [sys.executable, str(gate), "--message", "foo(x): add validation"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr


def test_the_skills_readme_records_the_vendored_provenance() -> None:
    assert "tlc-spec-lean" in _SKILLS_README
    assert "2.1.0" in _SKILLS_README, "the vendored version is recorded"
    assert "Per-batch Verifier" in _SKILLS_README and "Assisted-by: Claude Code" in _SKILLS_README
    assert "remove or rename" in _SKILLS_README, "the owner action that unshadows the copy"
    assert "Base directory" in _SKILLS_README, "how the owner confirms which copy loads"
    assert "revert" in _SKILLS_README, "the commit-contract authority deviation recorded"


# --- S9: the ship cycle runs on the lean skill with two lanes and the door gate ---


def test_shipcycle_lean_names_the_vendored_skill() -> None:
    assert "tlc-spec-driven" not in _SHIP_CYCLE
    frontmatter = _SHIP_CYCLE.split("---")[1]
    for token in ("tlc-spec-lean", "standard", "150k"):
        assert token in frontmatter, f"the description lacks {token!r}"
    intro = _between(_SHIP_CYCLE, "# Learny Ship Cycle", "**Autonomy contract:**")
    for token in ("tlc-spec-lean", "standard", "150k"):
        assert token in intro, f"the intro lacks {token!r}"
    stage1 = next(line for line in _SHIP_CYCLE.splitlines() if line.startswith("## Stage 1"))
    assert "tlc-spec-lean" in stage1, stage1


def test_shipcycle_stage_detection_maps_lean_artifacts() -> None:
    table = _between(_SHIP_CYCLE, "## Stage Detection", "## Stage 0")
    mapping = {
        "has `plan.md` but no `checks.md`": "Stage 1 (lean Plan)",
        "has `checks.md` but no `verification.md`": "Stage 1 (lean Build/Verify)",
    }
    rows = [line for line in table.splitlines() if line.strip().startswith("|")]
    for observation, stage in mapping.items():
        row = next((line for line in rows if observation in line), None)
        assert row is not None and stage in row, f"stage detection lost: {observation} -> {stage}"
    assert "verification.md" in table
    assert "validate_verification.py" in table and "--root" in table and "exits 0" in table, (
        "a Verifier PASS must be the gate script exiting 0"
    )


def test_shipcycle_lanes_pick_by_rule() -> None:
    stage0 = _between(_SHIP_CYCLE, "## Stage 0", "## Stage 1")
    for token in (
        "Lane S",
        "one sentence",
        "3 files or fewer",
        "no migration",
        "no new ADR",
        "no new route or screen",
        "no one-way door",
        "Lane F",
        "for everything else, including every roadmap row",
        "never downgrades",
    ):
        assert token in stage0, f"the lane rule lacks {token!r}"


def test_shipcycle_door_gate_stops_stage_1() -> None:
    stage1 = _between(_SHIP_CYCLE, "## Stage 1", "## Stage 2")
    assert "Door gate" in stage1
    gate = _between(stage1, "**Door gate", "**Escalation rule**")
    for token in (
        "one-way doors",
        "unconfirmed assumptions",
        "waived",
        "`auto`",
        "record the waiver in the plan",
    ):
        assert token in gate, f"the door gate lacks {token!r}"
    # The door gate is one of the two allowed stops: the contracts must say so, or the
    # default mode's binding rules forbid the very stop Stage 1 has to make.
    autonomy = _between(_SHIP_CYCLE, "**Autonomy contract:**", "**Continuation contract")
    continuation = _between(_SHIP_CYCLE, "**Continuation contract", "**Heartbeat")
    assert "two gates" in autonomy and "door gate" in autonomy, (
        "the autonomy contract names both gates"
    )
    assert "Stage 1 door gate" in continuation, (
        "the continuation contract allows the door-gate stop"
    )


def test_shipcycle_decisions_land_in_the_plan() -> None:
    stage1 = _between(_SHIP_CYCLE, "## Stage 1", "## Stage 2")
    for token in (
        "## Assumptions",
        "Confirmed? n",
        "never `y`",
        "## Landing",
        "AD-NNN",
        "binds other cycles",
    ):
        assert token in stage1, f"the auto-decision rule lacks {token!r}"


def test_shipcycle_batches_split_over_budget() -> None:
    stage1 = _between(_SHIP_CYCLE, "## Stage 1", "## Stage 2")
    for token in (
        "handoff",
        "slice boundaries",
        "sequential batches",
        "its own PR",
        "scoped to each batch's checks",
        "every check before the last batch's PR",
    ):
        assert token in stage1, f"the batch rule lacks {token!r}"


def test_shipcycle_cost_discipline_keeps_the_model_rows() -> None:
    discipline = _between(_SHIP_CYCLE, "## Cost discipline", "## Worker briefs")
    for row in _MODEL_ROWS:
        assert row in discipline, f"model row drifted: {row}"
    assert "one coherent piece" in discipline
    assert "checks.md" in discipline and "same commit" in discipline


# --- S10: review and finalize speak lean, with a legacy fallback ---


def test_review_track_a_reads_lean_with_the_legacy_path() -> None:
    track_a = _between(_PR_REVIEW, "### Track A", "### Track B")
    for token in ("plan.md", "checks.md", "verification.md", "`C`-id"):
        assert token in track_a, f"the lean path lacks {token!r}"
    for token in ("spec.md", "tasks.md", "validation.md", "FR-*"):
        assert token in track_a, f"the legacy path lacks {token!r}"


def test_finalize_internal_refs_forbid_slice_and_check_ids() -> None:
    assert "slice and check IDs" in _FINALIZE
    assert "`S2`" in _FINALIZE and "`C4`" in _FINALIZE
    assert "checks.md" in _FINALIZE, "checks.md is where internal traceability lives"
    assert "tasks.md" not in _FINALIZE, "tasks.md is the retired driven artifact"


def test_skills_docs_describe_the_vendored_copy() -> None:
    for doc in (_SKILLS_MD, _SKILLS_README):
        assert "tlc-spec-lean" in doc
        assert "vendored" in doc.lower()
        assert "the next harness cycle" not in doc, "the rewiring is done, not promised"
        # The README's provenance section must name the user-level copy it came from and
        # the owner action against it; what the indexes may not do is describe the skill
        # as user-level today or defer the vendoring to a future cycle.
        for stale in (
            "is a user-level skill",
            "user-level skill today",
            "moving to the user-level",
        ):
            assert stale not in doc, f"stale wording: {stale!r}"
    assert "three recorded project deviations" in _SKILLS_MD, (
        "the index counts the recorded deviations"
    )


def test_claude_profile_pins_the_lean_block() -> None:
    claude_md = (_REPO_ROOT / "CLAUDE.md").read_text()
    assert "## tlc-spec-lean" in claude_md
    block = _between(claude_md, "## tlc-spec-lean", "## ")
    assert "standard" in block and "150k" in block
    workflow = _between(claude_md, "## Workflow", "## ")
    assert "tlc-spec-lean" in workflow
    assert "tlc-spec-driven" not in claude_md


# --- S11: local worktrees stop being noise ---


def test_the_gitignore_worktrees_entry_exists() -> None:
    ignore = (_REPO_ROOT / ".gitignore").read_text()
    assert any(line.strip() == ".worktrees/" for line in ignore.splitlines()), ignore


# --- S12: the PR A checks re-run on any checkout ---


def test_the_proofs_portable_across_checkouts() -> None:
    proofs = [
        line[len("Proof:") :].strip().strip("`")
        for line in _CHECKS_MD.splitlines()
        if line.startswith("Proof:")
    ]
    assert len(proofs) >= 42, f"expected the full check set, found {len(proofs)} proofs"
    for proof in proofs:
        assert proof, "an empty Proof line"
        for bad in ("c:\\", "c:/", "/home/", "/users/", "/root/", "/tmp/", "/mnt/"):
            assert bad not in proof.lower(), f"absolute path in proof: {proof}"
        for pattern, why in (
            (r"[A-Za-z]:[\\/]", "drive-letter path"),
            (r"(?:^|[\s=])~[\\/]", "home-relative path"),
            (r"(?:^|[\s=\"'])/(?:[A-Za-z0-9_.-]+)", "POSIX root path"),
        ):
            assert not re.search(pattern, proof), f"{why} in proof: {proof}"
