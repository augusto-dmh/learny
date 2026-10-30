"""Sensors for the delivery harness's skills and docs (PR A's skill claims, PR B's loop).

PR A pruned the skill tree and rewired the attribution contract; PR B vendored the lean
spec skill into ``.claude/skills/tlc-spec-lean/`` and put the ship cycle, the review
lanes and the publishing conventions on it. These tests pin both at HEAD so a fresh
clone keeps the promises: the vendored tree is complete and carries its two recorded
deviations, the ship cycle detects lean artifact states and picks a lane by rule, review
reads lean artifacts with a legacy fallback, and every proof in the harness feature's
``checks.md`` runs wherever the repo is cloned.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

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


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True)


# --- S5: the harness loads only what it uses (PR A claims, re-proven portably) ---


def test_the_state_archive_is_intact_and_the_live_state_is_lean() -> None:
    archive = _REPO_ROOT / ".specs" / "project" / "archive" / "STATE-v1-v7.md"
    assert archive.is_file(), "the archived decision log is missing"
    # The archive must stay byte-identical to the state file it replaced. That equality
    # is frozen in the commit that created the archive, so compare against git history
    # when the objects are local (a shallow CI checkout sees one commit and skips this
    # half; the live-file structure below is the part that can still regress anywhere).
    added = _git(
        ["log", "--diff-filter=A", "--format=%H", "--", ".specs/project/archive/STATE-v1-v7.md"]
    )
    shas = added.stdout.decode().split()
    if added.returncode == 0 and shas:
        parent = _git(["rev-parse", f"{shas[0]}^"])
        if parent.returncode == 0:
            old = _git(["show", f"{parent.stdout.decode().strip()}:.specs/project/STATE.md"])
            assert old.returncode == 0, "the pre-archive state file left git history"

            # git show returns the stored blob (LF); a Windows checkout converts the
            # working tree to CRLF, so compare content with line endings normalized.
            def as_stored(raw: bytes) -> bytes:
                return raw.replace(b"\r\n", b"\n")

            assert as_stored(archive.read_bytes()) == as_stored(old.stdout), (
                "the archive no longer matches the original"
            )
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


def test_the_vendored_deviations_are_declared() -> None:
    skill = (_LEAN / "SKILL.md").read_text()
    section = skill.split("## Learny deviations", 1)[1]
    assert "per-batch" in section and "Verifier" in section, "the batch-scoped Verifier deviation"
    assert "D2" in section and "D3" in section, "both owner decisions named"
    assert "Assisted-by: Claude Code" in section, "the trailer deviation"
    assert "no-agent-trailer" in section, "the overridden lean rule named"


def test_the_vendored_build_override_requires_the_trailer() -> None:
    build = (_LEAN / "references" / "build.md").read_text()
    assert "Assisted-by: Claude Code" in build
    assert "every commit" in build
    assert "exception" in build and "no-agent-trailer rule" in build


def test_the_vendored_commit_gate_runs_on_this_interpreter() -> None:
    gate = _LEAN / "scripts" / "check_commit.py"
    good = subprocess.run(
        [sys.executable, str(gate), "--message", "feat(x): add validation"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
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
    assert "plan.md" in table and "Stage 1 (lean Plan)" in table
    assert "checks.md" in table and "Stage 1 (lean Build/Verify)" in table
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
        "every roadmap row",
        "never downgrades",
    ):
        assert token in stage0, f"the lane rule lacks {token!r}"


def test_shipcycle_door_gate_stops_stage_1() -> None:
    stage1 = _between(_SHIP_CYCLE, "## Stage 1", "## Stage 2")
    assert "Door gate" in stage1
    for token in (
        "one-way doors",
        "unconfirmed assumptions",
        "waived",
        "auto",
        "record the waiver in the plan",
    ):
        assert token in stage1, f"the door gate lacks {token!r}"


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
        assert not re.search(r"(?:^|\s)/(?:[A-Za-z0-9_.-]+/)+", proof), (
            f"POSIX absolute path in proof: {proof}"
        )
