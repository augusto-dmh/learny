# Learny MinIO image. MinIO withdrew its public container images (Docker Hub first,
# then quay.io/minio/minio started refusing anonymous pulls for every tag, including
# the release this deployment pins), so the server is built here from the official
# GitHub release binary instead — the same move deploy/backup made for `mc`.
#
# The image is deliberately dumb: the pinned static binary on Alpine plus curl for
# the compose healthcheck. Configuration (root credentials, data path, console
# address) stays exactly where it was — MINIO_ROOT_USER/PASSWORD from the compose
# env, `server /data --console-address ":9001"` from the compose command.
#
# The server runs as root, as the upstream image did: existing `minio_data` volumes
# are root-owned, and MinIO reaches nothing outside its own container (no host
# ports; S3 and console only on the compose network). Dropping to an unprivileged
# user is a recorded follow-up in ADR-0031 because it needs a one-time chown of
# every existing data volume, which is a migration step, not an image change.
FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

# Pinned MinIO server release — the same release the production overlay ran from
# quay, so a rebuilt image changes the distribution channel and nothing else.
ARG MINIO_RELEASE=RELEASE.2024-10-13T13-34-11Z
# Known-good sha256 of minio.linux-amd64.${MINIO_RELEASE}, hardcoded as a build-time
# constant (the release's published .sha256sum at pin time). Fetching the checksum
# same-origin as the binary would be trust-on-first-use; pinning the digest rejects
# any binary that is not the exact one vetted here. To bump the release, fetch the
# new release's published checksum and paste its digest.
ARG MINIO_SHA256=1126bbb3276321e7fed0167682d92a03572862f73802658f616af43d9a951e6a

# curl -> binary download at build time and the /minio/health/live healthcheck at
# run time; ca-certificates -> TLS to github.com.
RUN apk add --no-cache curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/minio \
       "https://github.com/minio/minio/releases/download/${MINIO_RELEASE}/minio.linux-amd64.${MINIO_RELEASE}" \
    && printf '%s  /usr/local/bin/minio\n' "$MINIO_SHA256" | sha256sum -c - \
    && chmod +x /usr/local/bin/minio

EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
