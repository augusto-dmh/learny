"""Every upstream container image is pinned by digest (ADR-0032).

A mutable tag lets upstream change what CI and a deploy run without a commit in
this repository; that rot broke CI twice in September. So every image the repo
pulls from someone else — a Dockerfile ``FROM`` or ``COPY --from=<image>``, a
Compose ``image:``, a workflow service container — is written
``<name>:<tag>@sha256:<64 hex>``. The tag stays for the reader; the digest is what
Docker resolves. Learny's own GHCR images are pinned by the deployed commit tag
instead, and build-stage names are not images at all.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_PINNED = re.compile(r"^[^\s@]+:[^\s@]+@sha256:[0-9a-f]{64}$")
_OWN_IMAGES = "ghcr.io/augusto-dmh/"


def _tracked(*patterns: str) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *patterns], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [_ROOT / line for line in out.splitlines() if line]


def _dockerfile_refs(path: Path) -> list[str]:
    stages: set[str] = set()
    refs: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        from_line = re.match(
            r"^FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", stripped, re.I
        )
        if from_line:
            image, stage = from_line.group(1), from_line.group(2)
            if image not in stages:
                refs.append(image)
            if stage:
                stages.add(stage)
            continue
        copy_from = re.search(r"--from=(\S+)", stripped)
        if stripped.upper().startswith("COPY") and copy_from:
            source = copy_from.group(1)
            if source not in stages and not source.isdigit():
                refs.append(source)
    return refs


def _compose_refs(path: Path) -> list[str]:
    services = (yaml.safe_load(path.read_text()) or {}).get("services", {}) or {}
    return [svc["image"] for svc in services.values() if "image" in svc]


def _workflow_refs(path: Path) -> list[str]:
    jobs = (yaml.safe_load(path.read_text()) or {}).get("jobs", {}) or {}
    refs = []
    for job in jobs.values():
        for service in (job.get("services") or {}).values():
            refs.append(service["image"])
    return refs


def _all_refs() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _tracked("*Dockerfile*"):
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _dockerfile_refs(path)]
    for path in _tracked("docker-compose*.yml"):
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _compose_refs(path)]
    for path in _tracked(".github/workflows/*.yml"):
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _workflow_refs(path)]
    return found


_UPSTREAM = [(src, ref) for src, ref in _all_refs() if not ref.startswith(_OWN_IMAGES)]


def test_the_scan_reaches_every_kind_of_image_reference() -> None:
    # Guard against a scan that silently finds nothing: each source kind the rule
    # covers must contribute at least one upstream reference today.
    sources = {src for src, _ in _UPSTREAM}
    assert any("Dockerfile" in s for s in sources)
    assert any(s.startswith("docker-compose") for s in sources)
    assert any(s.startswith(".github/workflows/") for s in sources)
    copy_from = _dockerfile_refs(_ROOT / "backend" / "Dockerfile")
    assert any("astral-sh/uv" in ref for ref in copy_from), "COPY --from images not scanned"


@pytest.mark.parametrize(("source", "ref"), _UPSTREAM, ids=lambda v: str(v))
def test_every_upstream_image_is_pinned_by_digest(source: str, ref: str) -> None:
    assert _PINNED.match(ref), f"{source}: {ref!r} must be '<name>:<tag>@sha256:<digest>'"


def test_adr_records_the_pin_rule_and_how_to_bump_a_digest() -> None:
    adrs = sorted((_ROOT / "docs" / "adr").glob("0032-*.md"))
    assert len(adrs) == 1, adrs
    text = adrs[0].read_text()
    status = next(line for line in text.splitlines() if line.startswith("- **Status**:"))
    assert status.startswith("- **Status**: Accepted"), status
    assert "@sha256:" in text
    assert "0031-build-minio-from-the-official-release-binary.md" in text
    assert "docker buildx imagetools inspect" in text, "the bump procedure must name the command"
