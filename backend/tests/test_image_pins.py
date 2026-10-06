"""Every upstream container image is pinned by digest (ADR-0032).

A mutable tag lets upstream change what CI and a deploy run without a commit in
this repository; that rot broke CI twice in September. So every image the repo
pulls from someone else — a Dockerfile ``FROM`` or ``COPY --from=<image>``, a
Compose ``image:``, a workflow service or job container, a ``uses: docker://``
step, or a ``docker run``/``docker pull`` in a workflow script — is written
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


def _script_refs(script: str) -> list[str]:
    # A ``docker run``/``docker pull`` in a step script pulls an image unless it
    # names a tag the same script just built. Flags make the image argument hard
    # to isolate, so an unbuilt command is reported whole: it passes only when the
    # image in it is pinned.
    joined = script.replace("\\\n", " ")
    built = set(re.findall(r"docker build\b[^\n]*?-t\s+(\S+)", joined))
    refs = []
    for command in re.findall(r"docker (?:run|pull)\b[^\n]*", joined):
        if any(tag in command.split() for tag in built):
            continue
        pinned = re.search(r"\S+@sha256:[0-9a-f]{64}", command)
        refs.append(pinned.group(0) if pinned else command.strip())
    return refs


def _workflow_refs(workflow: dict) -> list[str]:
    refs = []
    for job in (workflow.get("jobs") or {}).values():
        for service in (job.get("services") or {}).values():
            refs.append(service["image"])
        container = job.get("container")
        if container:
            refs.append(container if isinstance(container, str) else container["image"])
        for step in job.get("steps") or []:
            uses = str(step.get("uses", ""))
            if uses.startswith("docker://"):
                refs.append(uses.removeprefix("docker://"))
            refs += _script_refs(str(step.get("run", "")))
    return refs


def _all_refs() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _tracked("*Dockerfile*"):
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _dockerfile_refs(path)]
    for path in _tracked("docker-compose*.yml", "docker-compose*.yaml", "compose*.y*ml"):
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _compose_refs(path)]
    for path in _tracked(".github/workflows/*.yml", ".github/workflows/*.yaml"):
        workflow = yaml.safe_load(path.read_text()) or {}
        found += [(str(path.relative_to(_ROOT)), ref) for ref in _workflow_refs(workflow)]
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


def test_the_workflow_scan_sees_every_way_a_job_pulls_an_image() -> None:
    # Negative control: each form a workflow can pull an upstream image through
    # is reported, and a tag the same script built is not.
    digest = "@sha256:" + "0" * 64
    workflow = {
        "jobs": {
            "a": {"container": "node:20"},
            "b": {"container": {"image": "python:3.13" + digest}},
            "c": {"steps": [{"uses": "docker://alpine:3"}]},
            "d": {
                "steps": [
                    {"run": "docker pull postgres:16"},
                    {"run": "docker run --rm -e A=b \\\n  redis:7 redis-cli ping"},
                    {"run": "docker build -t learny-x:ci .\ndocker run -d learny-x:ci"},
                ]
            },
        }
    }
    refs = _workflow_refs(workflow)
    assert [bool(_PINNED.match(r)) for r in refs] == [False, True, False, False, False], refs


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
