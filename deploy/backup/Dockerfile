# Learny backup image (RFC-003 Cycle A). A small self-contained Alpine image that
# runs scheduled PostgreSQL dumps plus optional offsite object mirroring via crond,
# and ships a manual restore script. It talks to db/minio over the compose network
# only and needs no host access, so it runs as the default user.
FROM alpine:3.22

# Pinned MinIO client release. Verified to exist before pinning.
ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
# Known-good sha256 of mc.${MC_RELEASE} (linux-amd64), hardcoded as a build-time
# constant. Fetching the checksum same-origin as the binary would be trust-on-first-use:
# an upstream re-cut under the same release name would be silently accepted. Pinning the
# digest here rejects any binary that is not the exact one vetted at pin time. To bump the
# release, fetch the new release's published checksum and paste its digest. The binary
# downloads from the minio/mc GitHub releases: dl.min.io stopped serving mc (410 for
# every release, including latest) when MinIO withdrew its public distributions — the
# GitHub artifact of this release is byte-identical (same sha256) to the old dl.min.io one.
ARG MC_SHA256=01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891

# postgresql16-client -> pg_dump/pg_restore AND pg_basebackup (matches the pg16
# server image); flock -> single-run guard; curl -> heartbeat + mc download;
# ca-certificates -> TLS to the offsite S3 endpoint and the heartbeat URL.
RUN apk add --no-cache postgresql16-client curl flock ca-certificates \
    && curl -fsSL -o /usr/local/bin/mc \
       "https://github.com/minio/mc/releases/download/${MC_RELEASE}/mc.linux-amd64.${MC_RELEASE}" \
    && printf '%s  /usr/local/bin/mc\n' "$MC_SHA256" | sha256sum -c - \
    && chmod +x /usr/local/bin/mc

COPY backup.sh restore.sh backup-now base-backup.sh base-backup-now \
     wal-archive.sh restore-pitr.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh \
             /usr/local/bin/backup-now /usr/local/bin/base-backup.sh \
             /usr/local/bin/base-backup-now /usr/local/bin/wal-archive.sh \
             /usr/local/bin/restore-pitr.sh /usr/local/bin/entrypoint.sh

# mc stores its aliases under this directory; keep it stable and writable.
ENV HOME=/root MC_CONFIG_DIR=/root/.mc

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
