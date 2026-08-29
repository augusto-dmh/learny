# Learny PostgreSQL image (RFC-005 Cycle E). A thin derivative of the stock
# pgvector image that exists to solve exactly two problems declaratively, so that
# a clean deploy archives WAL without any host-side step:
#
#  1. Volume ownership. Docker creates a fresh named volume root-owned when the
#     mount path is ABSENT from the image, and copies the image path's ownership
#     and mode when it is PRESENT. `archive_command` runs as the unprivileged
#     `postgres` user, so an archive volume mounted at a path the image never
#     declared fails at runtime with a permission error far from its cause.
#     Creating /wal_archive here, owned by postgres, is what makes the volume
#     writable — no entrypoint wrapper, no chown on the host.
#
#  2. Replication authentication. The stock entrypoint generates a pg_hba.conf
#     whose only remote rule is `host all all all <auth>`, and PostgreSQL's `all`
#     database keyword deliberately does NOT match physical replication
#     connections. `pg_basebackup` from the backup sidecar is therefore refused
#     ("no pg_hba.conf entry for replication connection from host ..."). The
#     shipped pg_hba.conf adds the missing replication rule under the SAME
#     scram-sha-256 authentication the remote rule already uses, and is selected
#     with `-c hba_file=` from the compose command so it also applies to data
#     directories that already exist.
#
# The image carries no credentials: the password stays in POSTGRES_PASSWORD from
# the env_file, exactly as before.
FROM pgvector/pgvector:pg16

# Archive target for archive_command. 0700 and postgres-owned: the db writes it,
# and the backup sidecar (which runs as root) reads and prunes it.
RUN install -d -o postgres -g postgres -m 0700 /wal_archive

# Outside PGDATA so it survives an existing data volume; world-readable content
# with no secrets in it.
COPY pg_hba.conf /etc/postgresql/pg_hba.conf
RUN chown postgres:postgres /etc/postgresql/pg_hba.conf \
    && chmod 0644 /etc/postgresql/pg_hba.conf
