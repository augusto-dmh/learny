# Learny backup image (RFC-003 Cycle A). A small self-contained Alpine image that
# runs scheduled PostgreSQL dumps plus optional offsite object mirroring via crond,
# and ships a manual restore script. It talks to db/minio over the compose network
# only and needs no host access, so it runs as the default user.
FROM alpine:3.22

# Pinned MinIO client release. Verified to exist on dl.min.io before pinning
# (the binary and its .sha256sum both resolve); the checksum is enforced below.
ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z

# postgresql16-client -> pg_dump/pg_restore (matches the pg16 server image);
# flock -> single-run guard; curl -> heartbeat + mc download; ca-certificates -> TLS
# to the offsite S3 endpoint and the heartbeat URL.
RUN apk add --no-cache postgresql16-client curl flock ca-certificates \
    && curl -fsSL -o /usr/local/bin/mc \
       "https://dl.min.io/client/mc/release/linux-amd64/mc.${MC_RELEASE}" \
    && curl -fsSL -o /tmp/mc.sha256sum \
       "https://dl.min.io/client/mc/release/linux-amd64/mc.${MC_RELEASE}.sha256sum" \
    && printf '%s  /usr/local/bin/mc\n' "$(cut -d' ' -f1 /tmp/mc.sha256sum)" | sha256sum -c - \
    && rm -f /tmp/mc.sha256sum \
    && chmod +x /usr/local/bin/mc

COPY backup.sh restore.sh backup-now entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh \
             /usr/local/bin/backup-now /usr/local/bin/entrypoint.sh

# mc stores its aliases under this directory; keep it stable and writable.
ENV HOME=/root MC_CONFIG_DIR=/root/.mc

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
