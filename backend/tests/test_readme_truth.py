"""The README's truth claims are pinned to the repository (unit).

The README is the project's front page, and it drifted four roadmaps behind
`main` once. These checks read `README.md` and compare each claim that names a
release, a shipped roadmap, a decision-record count, or a demo asset against the
files the claim is about, so the offline suite fails on the next drift instead
of a reader noticing it months later. Content is asserted, not executed.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_README = (_ROOT / "README.md").read_text()
_MEDIA_GUIDE = (_ROOT / "docs" / "media" / "README.md").read_text()

_CURRENT_RELEASE = "v0.7.0"
_SHIPPED_RFCS = (
    "docs/rfc/0004-student-experience-roadmap.md",
    "docs/rfc/0005-evidence-gated-hardening-roadmap.md",
    "docs/rfc/0006-reading-first-ux-overhaul.md",
    "docs/rfc/0007-public-launch-roadmap.md",
)


def _section(heading: str) -> str:
    """Return the body of the README section that starts at ``heading``."""
    start = _README.index(f"\n{heading}\n")
    level = heading.split(" ", 1)[0]
    rest = _README[start + 1 :]
    match = re.search(rf"^{re.escape(level)} ", rest[len(heading) :], flags=re.MULTILINE)
    return rest if match is None else rest[: len(heading) + match.start()]


# --- The status paragraph names the current release ------------------------------


def test_status_paragraph_names_the_current_release_and_not_a_superseded_one() -> None:
    status = next(line for line in _README.splitlines() if line.startswith("> Status:"))
    assert f"**{_CURRENT_RELEASE}**" in status
    assert "v3 shipped" not in _README


# --- The roadmap section lists every shipped arc and the unscheduled candidates ----


def test_roadmap_section_lists_each_shipped_rfc_with_a_link() -> None:
    roadmap = _section("## Roadmap")
    for rfc in _SHIPPED_RFCS:
        assert f"]({rfc})" in roadmap, rfc
        assert (_ROOT / rfc).is_file(), rfc
    shipped_bullets = [line for line in roadmap.splitlines() if line.startswith("- ✅")]
    assert len(shipped_bullets) >= len(_SHIPPED_RFCS)


def test_roadmap_section_names_the_recorded_candidates_as_not_scheduled() -> None:
    roadmap = _section("## Roadmap")
    candidates = roadmap[roadmap.index("Recorded candidates, not scheduled") :]
    assert "economy generation profile" in candidates
    assert "Bring-your-own API keys" in candidates


# --- The decision-record counts equal the files on disk --------------------------


def test_engineering_process_counts_match_the_decision_record_directories() -> None:
    process = _section("## Engineering process")
    adr_claim = re.search(r"(\d+) \[ADRs\]\(docs/adr/\)", process)
    rfc_claim = re.search(r"(\d+) \[RFCs\]\(docs/rfc/\)", process)
    assert adr_claim is not None and rfc_claim is not None
    assert int(adr_claim.group(1)) == len(list((_ROOT / "docs" / "adr").glob("*.md")))
    assert int(rfc_claim.group(1)) == len(list((_ROOT / "docs" / "rfc").glob("*.md")))


# --- The demo section embeds only assets that exist ------------------------------


def _demo_assets() -> list[str]:
    # The capture guide is the single list of asset slots (`docs/media/<file>`).
    names = re.findall(r"`docs/media/((?:demo\.gif|screenshot-[a-z]+\.png))`", _MEDIA_GUIDE)
    assert names, "the media guide names no asset slots"
    return sorted(set(names))


def test_demo_section_embeds_present_assets_and_declares_the_rest_pending() -> None:
    demo = _section("## Demo")
    embedded = set(re.findall(r"!\[[^\]]*\]\(docs/media/([^)]+)\)", demo))
    for name in _demo_assets():
        present = (_ROOT / "docs" / "media" / name).is_file()
        if present:
            assert name in embedded, f"{name} exists but is not embedded"
        else:
            assert name not in embedded, f"{name} is embedded but missing"
    if embedded != set(_demo_assets()):
        assert "not recorded yet" in demo
        assert "docs/media/README.md" in demo
