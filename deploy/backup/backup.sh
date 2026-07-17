#!/bin/sh
# Scheduled PostgreSQL dump + optional offsite mirror (RFC-003 Cycle A).
#
# Contract (spec OPS-04..08):
#   * single-run guard via `flock -n` -- a second concurrent run exits without dumping
#   * `pg_dump -Fc` to a temp name, renamed onto the final name only on success, so a
#     failed dump never leaves a partial archive under the final name nor touches priors
#   * offsite work runs only when ALL four LEARNY_BACKUP_REMOTE_* vars are set; otherwise
#     the run logs "offsite not configured" and still finishes the local dump
#   * local (and, when configured, offsite) dumps older than KEEP_DAYS are pruned only
#     after a successful dump, with the newest archive always exempt
#   * the heartbeat is requested last and only on a fully successful run
set -eu

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=learny}"
: "${POSTGRES_DB:=learny}"
: "${LEARNY_BACKUP_DIR:=/backups/db}"
: "${LEARNY_BACKUP_KEEP_DAYS:=14}"
: "${LEARNY_BACKUP_SOURCE_ENDPOINT:=http://minio:9000}"
: "${LEARNY_BACKUP_SOURCE_BUCKET:=learny-sources}"
: "${LEARNY_BACKUP_LOCK:=/tmp/learny-backup.lock}"

log() { echo "[backup] $*"; }

# --- single-run guard (OPS-07) -------------------------------------------------
# Hold an exclusive lock on fd 9 for the life of the run. `flock -n` fails
# immediately if another run holds it, so the second invocation leaves without
# dumping (and without pinging the heartbeat).
exec 9>"$LEARNY_BACKUP_LOCK"
if ! flock -n 9; then
  log "another backup run holds the lock; exiting without dumping"
  exit 0
fi

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

mkdir -p "$LEARNY_BACKUP_DIR"
stamp="$(date -u +%Y-%m-%d-%H%M%S)"
archive="$LEARNY_BACKUP_DIR/learny-$stamp.dump"
tmp="$archive.tmp"

# A failed dump must leave no partial archive under the final name; drop our temp.
trap 'rm -f "$tmp"' EXIT

# --- dump (OPS-04): temp name, renamed onto the final name only on success -----
log "dumping $POSTGRES_DB@$POSTGRES_HOST -> $archive"
pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$tmp"
mv "$tmp" "$archive"
log "wrote $archive"

# --- offsite (OPS-05): only when ALL four remote vars are set ------------------
offsite=0
if [ -n "${LEARNY_BACKUP_REMOTE_ENDPOINT:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_ACCESS_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_SECRET_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_BUCKET:-}" ]; then
  offsite=1
  log "offsite configured; copying dump and mirroring objects"
  mc alias set learny_offsite "$LEARNY_BACKUP_REMOTE_ENDPOINT" \
    "$LEARNY_BACKUP_REMOTE_ACCESS_KEY" "$LEARNY_BACKUP_REMOTE_SECRET_KEY"
  mc cp "$archive" "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/db/"
  # Mirror the source bucket WITHOUT --remove: objects deleted in the app persist
  # offsite (favors recoverability; documented in docs/ops/backups.md).
  mc alias set learny_source "$LEARNY_BACKUP_SOURCE_ENDPOINT" \
    "${MINIO_ROOT_USER:?MINIO_ROOT_USER must be set}" \
    "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be set}"
  mc mirror --overwrite "learny_source/$LEARNY_BACKUP_SOURCE_BUCKET" \
    "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/objects"
else
  log "offsite not configured"
fi

# --- prune (OPS-06): after a successful dump; newest archive always exempt -----
newest="$(ls -1t "$LEARNY_BACKUP_DIR"/learny-*.dump 2>/dev/null | head -n1)"
find "$LEARNY_BACKUP_DIR" -maxdepth 1 -type f -name 'learny-*.dump' \
  -mtime "+$LEARNY_BACKUP_KEEP_DAYS" ! -path "$newest" -print -delete
if [ "$offsite" -eq 1 ]; then
  # The dump just uploaded is age 0, so an --older-than KEEP_DAYS window never
  # removes it (offsite newest-exemption).
  mc rm --recursive --force --older-than "${LEARNY_BACKUP_KEEP_DAYS}d" \
    "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/db/"
fi

# --- heartbeat (OPS-08): last, only on a fully successful run ------------------
if [ -n "${LEARNY_BACKUP_HEARTBEAT_URL:-}" ]; then
  log "pinging heartbeat"
  curl -fsS -o /dev/null "$LEARNY_BACKUP_HEARTBEAT_URL"
fi

log "backup complete"
