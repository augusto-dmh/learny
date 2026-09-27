"""Version consistency across the README, the backend, and the frontend (unit).

The README's status paragraph names the current release; both package manifests
must declare that same version, so a release cut against one of them can never
disagree with the other or with the front page.
"""

import json
import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _readme_release() -> str:
    status = next(
        line
        for line in (_REPO_ROOT / "README.md").read_text().splitlines()
        if line.startswith("> Status:")
    )
    match = re.search(r"\*\*v(\d+\.\d+\.\d+)\*\*", status)
    assert match is not None, "the README status paragraph names no **vX.Y.Z** release"
    return match.group(1)


def test_backend_version_matches_the_readme_release() -> None:
    with open(_REPO_ROOT / "backend" / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == _readme_release()


def test_frontend_version_matches_the_readme_release() -> None:
    with open(_REPO_ROOT / "frontend" / "package.json") as f:
        data = json.load(f)
    assert data["version"] == _readme_release()


def test_frontend_lockfile_root_matches_the_manifest() -> None:
    with open(_REPO_ROOT / "frontend" / "package-lock.json") as f:
        lock = json.load(f)
    with open(_REPO_ROOT / "frontend" / "package.json") as f:
        manifest = json.load(f)
    assert lock["version"] == manifest["version"]
    assert lock["packages"][""]["version"] == manifest["version"]
