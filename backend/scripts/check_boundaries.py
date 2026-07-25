#!/usr/bin/env python3
"""Architecture fitness check — the ports/adapters boundaries as executable rules.

Encodes the accepted decisions on provider isolation and layering (see
docs/adr/0007, 0009, 0019, 0020) so a violation fails lint/CI instead of
relying on review prose:

1. Provider SDKs (openai, anthropic, boto3, botocore, docling, ebooklib) are
   imported only under ``app/infrastructure/`` (adapters) or ``app/eval/`` (the
   eval harness is an accepted edge — e.g. the live judge) — lazy in-function
   imports count.
2. ``app/domain/`` imports no framework or outer layer: fastapi, sqlalchemy,
   celery, redis, provider SDKs, app.infrastructure, app.application, app.worker.
3. ``app/application/`` and ``app/eval/`` never import ``app.infrastructure``;
   adapters are injected by the composition root.

Stdlib-only. Exit 0 = clean, exit 1 = violations listed on stdout.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"

PROVIDER_SDKS = "openai|anthropic|boto3|botocore|docling|ebooklib"
SDK_IMPORT = re.compile(rf"^\s*(?:import|from)\s+(?:{PROVIDER_SDKS})\b")
DOMAIN_FORBIDDEN = re.compile(
    rf"^\s*(?:import|from)\s+(?:fastapi|sqlalchemy|celery|redis|{PROVIDER_SDKS})\b"
)
DOMAIN_OUTWARD = re.compile(r"^\s*(?:import|from)\s+app\.(?:infrastructure|application|worker)\b")
INFRA_IMPORT = re.compile(r"^\s*(?:import|from)\s+app\.infrastructure\b")


def main() -> int:
    violations: list[str] = []
    for py in sorted(APP.rglob("*.py")):
        rel = py.relative_to(BACKEND).as_posix()
        if "__pycache__" in rel:
            continue
        sdk_allowed = rel.startswith(("app/infrastructure/", "app/eval/"))
        in_domain = rel.startswith("app/domain/")
        in_ported_layer = rel.startswith(("app/application/", "app/eval/"))
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if not sdk_allowed and SDK_IMPORT.match(line):
                violations.append(
                    f"{rel}:{lineno}: provider SDK import outside app/infrastructure/"
                    f" or app/eval/ — {line.strip()}"
                )
            if in_domain and (DOMAIN_FORBIDDEN.match(line) or DOMAIN_OUTWARD.match(line)):
                violations.append(
                    f"{rel}:{lineno}: domain layer imports outward — {line.strip()}"
                )
            if in_ported_layer and INFRA_IMPORT.match(line):
                violations.append(
                    f"{rel}:{lineno}: {rel.split('/')[1]} layer imports app.infrastructure"
                    f" directly — {line.strip()}"
                )
    if violations:
        print(f"{len(violations)} architecture boundary violation(s):")
        for v in violations:
            print(f"  {v}")
        return 1
    print("architecture boundaries clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
