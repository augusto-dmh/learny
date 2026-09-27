"""The README's truth claims are pinned to the repository (unit).

The README is the project's front page, and it drifted four roadmaps behind
`main` once. These checks read `README.md` and compare each claim that names a
release, a shipped roadmap, a decision-record count, or a demo asset against the
files the claim is about, so the offline suite fails on the next drift instead
of a reader noticing it months later. Content is asserted, not executed.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_README = (_ROOT / "README.md").read_text()
_MEDIA_GUIDE = (_ROOT / "docs" / "media" / "README.md").read_text()

# The release the README must name is the one the backend manifest declares
# (test_versions.py pins the frontend manifest and lock to the same value), so a
# release cut edits the manifests and the README — never a test constant.
with open(_ROOT / "backend" / "pyproject.toml", "rb") as _pyproject:
    _CURRENT_RELEASE = "v" + tomllib.load(_pyproject)["project"]["version"]
# The arcs this README must list as shipped. The test also reads every RFC a ✅
# bullet links and requires the RFC itself to say it was accepted.
_SHIPPED_RFCS = (
    "docs/rfc/0002-learny-v2-roadmap.md",
    "docs/rfc/0003-learny-v3-roadmap.md",
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


def _shipped_bullet_links() -> dict[str, str]:
    """Map each RFC linked from a ``- ✅`` roadmap bullet to that bullet."""
    roadmap = _section("## Roadmap")
    links: dict[str, str] = {}
    for line in roadmap.splitlines():
        if line.startswith("- ✅"):
            for rfc in re.findall(r"\]\((docs/rfc/[^)]+\.md)\)", line):
                links[rfc] = line
    return links


def test_roadmap_section_lists_each_shipped_rfc_with_a_link() -> None:
    # The link and the shipped marker must sit on the same bullet: a link
    # elsewhere in the section does not make the arc "shipped".
    links = _shipped_bullet_links()
    for rfc in _SHIPPED_RFCS:
        assert (_ROOT / rfc).is_file(), rfc
        assert rfc in links, rfc


def test_every_rfc_the_roadmap_calls_shipped_says_so_itself() -> None:
    # A ✅ bullet is a claim about the RFC; the RFC's own status line must agree,
    # or the front page calls an arc shipped that its decision record still
    # holds open (RFC-005 and RFC-006 sat in that state for two months).
    links = _shipped_bullet_links()
    assert links, "no ✅ bullet links an RFC"
    for rfc in links:
        status = next(
            line
            for line in (_ROOT / rfc).read_text().splitlines()
            if line.startswith("- **Status**:")
        )
        assert status.startswith("- **Status**: Accepted"), (rfc, status)


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
    # Any embed of a docs/media file must resolve — not only the named slots.
    for name in embedded:
        assert (_ROOT / "docs" / "media" / name).is_file(), f"{name} is embedded but missing"
    slots = _demo_assets()
    for name in slots:
        if (_ROOT / "docs" / "media" / name).is_file():
            assert name in embedded, f"{name} exists but is not embedded"
    if embedded != set(slots):
        assert "not recorded yet" in demo
        assert "docs/media/README.md" in demo


# --- The deployment section names every image the deploy workflow publishes -----


def test_deployment_section_counts_and_names_the_published_images() -> None:
    # The old sentence said "three images" for two roadmaps after the matrix grew
    # to five; the count and the brace list are derived from the matrix here.
    workflow = yaml.safe_load((_ROOT / ".github" / "workflows" / "deploy.yml").read_text())
    names = [entry["name"] for entry in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    number_words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    section = _section("### Deployment (CI → GHCR → VPS)")
    assert f"publishes {number_words[len(names)]} images" in section
    short = ",".join(name.removeprefix("learny-") for name in names)
    assert f"`ghcr.io/augusto-dmh/learny-{{{short}}}`" in section
