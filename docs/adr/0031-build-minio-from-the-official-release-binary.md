# ADR-031: Build The MinIO Image From The Official Release Binary

- **Date**: 2026-09-27
- **Status**: Accepted (2026-09-27, rides the implementing cycle's merge gate)
- **Deciders**: Augusto, Claude
- **Tags**: operations, storage, docker, supply-chain

## Context and Problem Statement

Learny stores uploaded books in S3-compatible object storage, self-hosted as MinIO in both the local and the production Compose stacks (ADR-0013; decision AD-008). Until now the stack pulled MinIO's own container image: first from Docker Hub, then — when MinIO withdrew its Docker Hub distribution — from `quay.io/minio/minio`, pinned to `RELEASE.2024-10-13T13-34-11Z` in production and `latest` locally.

On 2026-09-26 `quay.io/minio/minio` began refusing anonymous pulls for every tag, including the pinned release, while other public quay repositories still pull. `dl.min.io` answers 410 for the server binary as it already did for the `mc` client (see `deploy/backup/Dockerfile`). Every path that pulls the image now fails: CI's `backend-test` job (a plain `docker run`), the `compose-smoke` job, a fresh `docker compose up --build` from the README, and any VPS that has not cached the image. Pull request #72 was the first to hit it.

MinIO still publishes the server as a static binary on its GitHub releases, with a checksum per asset, for the pinned release and for later ones.

## Decision Drivers

- The stack must boot from a clean clone with no registry credentials, as the README promises.
- The production release stays pinned and is bumped deliberately, never by a floating tag.
- The binary's provenance is verified at build time, not trusted on first use.
- No new storage provider: ADR-0013's S3-compatible boundary and the MinIO choice stand.

## Considered Options

1. **Build a Learny MinIO image from the official GitHub release binary, sha256-pinned** (`deploy/minio/Dockerfile`), published to GHCR beside the other app images. ⭐
2. Switch to a third-party MinIO packaging (`bitnamilegacy/minio`, a frozen namespace) — pulls today, receives no updates, and its entrypoint and paths differ from upstream's.
3. Switch to another S3-compatible server (RustFS, Garage, SeaweedFS) — reopens ADR-0013's choice for a distribution problem, and every backup and restore script speaks MinIO's `mc`.
4. Authenticate to quay.io in CI and on the VPS — requires an account whose terms and future are the very thing that just changed.

## Decision Outcome

Option 1. `deploy/minio/Dockerfile` downloads `minio.linux-amd64.<release>` from `github.com/minio/minio/releases`, checks it against a digest hard-coded in the Dockerfile (the release's published `.sha256sum` at pin time — the same trust model as the `mc` pin in the backup image), and runs it as the entrypoint on Alpine. The base Compose file builds the service from that directory; the production overlay pulls `ghcr.io/augusto-dmh/learny-minio:${LEARNY_IMAGE_TAG}` like every other app image; the deploy workflow adds it to the image matrix; CI's backend job builds it in place of the `docker run` pull. The pinned release is unchanged (`RELEASE.2024-10-13T13-34-11Z`), so the running deployment changes distribution channel and nothing else. The healthcheck moves from `mc ready local` (a client the upstream image bundled) to `curl` against `/minio/health/live`.

### Consequences

- Good: the stack boots from a clean clone again; CI and deploys no longer depend on a registry MinIO controls; the binary's digest is under version control.
- Good: bumping MinIO is one Dockerfile change with a fresh digest, reviewed like any other dependency.
- Bad: the image is ours to rebuild when MinIO publishes a security release; nothing upstream notifies us. Dependabot does not track it.
- Bad: one more image in the deploy matrix (~100 MB, single stage).
- Bad: the server still runs as root inside its container, as the upstream image did (parity, not a regression). Dropping privileges needs a one-time `chown` of every existing `minio_data` volume plus a `USER` line, so it is a follow-up with its own runbook step, recorded here rather than done silently.
- Operator step: GHCR creates `learny-minio` as a private package on its first push; it must be flipped to public (the deploy runbook lists it) before a VPS can pull it.
- Watch: if MinIO stops publishing GitHub release assets as well, option 3 becomes the fallback and gets its own decision.
