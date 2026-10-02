# ADR-032: Pin Every Upstream Container Image By Digest

- **Date**: 2026-10-02
- **Status**: Accepted (2026-10-02, rides the implementing cycle's merge gate)
- **Deciders**: Augusto, Claude
- **Tags**: operations, docker, supply-chain, ci

## Context and Problem Statement

Learny builds and runs on images other people publish: `python`, `node`, `alpine`, `pgvector/pgvector`, `redis`, `caddy`, `netdata` and the `uv` image its backend copies a binary from. Each was referenced by a tag (`node:20-slim`, `redis:7-alpine`, `pgvector/pgvector:pg16`). A tag is a pointer the publisher can move or withdraw, so CI, a local `docker compose up --build` and a deploy could run different bytes than the last green build without any commit in this repository.

That happened twice in September 2026: MinIO's image moved and then refused anonymous pulls, breaking CI on two consecutive pull requests. [ADR-0031](0031-build-minio-from-the-official-release-binary.md) answered the MinIO case by building from a release binary whose sha256 is under version control. Every other upstream image kept floating.

## Decision Drivers

- What CI builds must be what the repository says, until a commit changes it.
- A reader must still see which version is in use without decoding a hash.
- The rule must be enforced by a test, not remembered.
- No new tooling or registry account.

## Considered Options

1. **Pin each upstream reference as `<name>:<tag>@sha256:<index digest>`, enforced by a test that scans every Dockerfile, Compose file and workflow service.** ⭐
2. Digest only (`<name>@sha256:…`) — equally reproducible, but nobody can tell `node` 20 from 22 in a diff.
3. Keep tags and add Dependabot's `docker` ecosystem — keeps tags fresh, but still lets upstream change a tag between two runs of the same commit, and opens version-bump pull requests the repository already turned off for pip and npm.
4. Mirror every image into GHCR — reproducible, but one more image to rebuild for every upstream security release, as ADR-0031 already accepted for MinIO alone.

## Decision Outcome

Option 1. Every image the repository pulls from someone else is written with its tag and the multi-architecture index digest, for example `node:20-slim@sha256:2cf0…bfc0`. Docker resolves the digest and ignores the tag; the tag stays for the reader. This covers Dockerfile `FROM` lines, `COPY --from=<image>`, Compose `image:` keys and GitHub Actions service containers. Learny's own `ghcr.io/augusto-dmh/` images are exempt: they are already pinned to the deployed commit tag. `backend/tests/test_image_pins.py` fails on any upstream reference without a digest.

### Bumping a digest

1. Resolve the current index digest for the tag: `docker buildx imagetools inspect <name>:<tag>` and copy the top-level `Digest:`.
2. Replace the digest everywhere that tag appears (`git grep '<name>:<tag>@'`), keeping the tag, or change the tag and the digest together for a version bump.
3. Run `make check`; the compose smoke job in CI rebuilds the stack on the new bytes.

### Consequences

- Good: a commit fully determines what CI and a deploy build; upstream rot shows up as a deliberate bump that fails or passes in review, not as a red run on an unrelated pull request.
- Good: the pin rule is executable, so a new image cannot land without one.
- Bad: security fixes published under the same tag no longer arrive on their own; nothing notifies the repository. Bumps are a deliberate chore, the same trust model ADR-0031 accepted for MinIO.
- Bad: lines get longer, and a digest in a diff is unreadable without its tag (hence the tag stays).
- Watch: if bumps are forgotten for months, add a scheduled job that reports stale digests rather than reverting to tags.
