#!/bin/sh
# Scheduled physical base backup (RFC-005 Cycle E).
#
# Archived WAL segments are not a recovery chain on their own: replay needs a
# PHYSICAL base with a known WAL position to replay onto, and a `pg_dump` archive
# carries no such position. This job produces that base. It complements the
# nightly logical dump (backup.sh) rather than replacing it — the dump remains the
# version-portable, selective-restore path.
#
# Contract (spec PITR-03, PITR-04, PITR-06):
#   * shares backup.sh's lock -- a base backup and a dump are both heavy
#     full-database reads over the same disk and the same /backups volume, so the
#     second to arrive exits without corrupting either artifact
#   * `pg_basebackup -Ft` into a temp directory, renamed onto the final name only on
#     success, so a failed run leaves no partial artifact and touches no prior base
#   * records the base's START WAL segment beside it -- this is what makes WAL
#     retention derivable from a retained base instead of from age alone. The
#     segment is read from the server BEFORE the copy starts, which can only place
#     the floor at or before the base's real start and therefore only ever retains
#     more WAL than strictly needed
#   * offsite work runs only when ALL four LEARNY_BACKUP_REMOTE_* vars are set;
#     otherwise the run logs "offsite not configured" and still finishes locally
#   * pruning runs only after a successful backup, with the newest base always exempt
# Runs under the image's busybox ash (alpine), which supports `pipefail`.
set -euo pipefail

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=learny}"
: "${POSTGRES_DB:=learny}"
: "${LEARNY_BASEBACKUP_DIR:=/backups/base}"
: "${LEARNY_BACKUP_KEEP_DAYS:=14}"
: "${LEARNY_BACKUP_LOCK:=/tmp/learny-backup.lock}"

log() { echo "[base-backup] $*"; }

# --- single-run guard, SHARED with the nightly dump (PITR-03) -------------------
# Deliberately the same lock file backup.sh takes. The default schedules are 90
# minutes apart, so a collision means an on-demand run overlapped a scheduled one;
# skipping is logged rather than silent so a repeatedly-skipped base is visible.
exec 9>"$LEARNY_BACKUP_LOCK"
if ! flock -n 9; then
  log "another backup run holds the lock; exiting without taking a base backup"
  exit 0
fi

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

mkdir -p "$LEARNY_BASEBACKUP_DIR"
stamp="$(date -u +%Y-%m-%d-%H%M%S)"
base="$LEARNY_BASEBACKUP_DIR/learny-base-$stamp"
tmp="$base.tmp"

# A failed backup must leave no partial artifact under the final name; drop our temp.
trap 'rm -rf "$tmp"' EXIT
rm -rf "$tmp"

# --- record the replay floor (PITR-05's input), BEFORE the copy starts ----------
# WAL retention is derived from this segment, so the one recorded must never sit
# LATER than the segment the base actually starts replaying from: a floor past it
# prunes WAL the base still needs, and that base is then unrecoverable. Asking the
# server for its current segment BEFORE the backup starts is conservative by
# construction — WAL only moves forward, so the checkpoint pg_basebackup takes can
# only be at or after this point, and an earlier floor only ever retains MORE. CI
# asserts the direction against the finished base's own label.
#
# This replaces reading backup_label out of the finished archive, which gunzipped
# the whole cluster tarball to reach ~200 bytes (busybox tar has no early exit and a
# gzip stream is not seekable): O(cluster) CPU and IO on every weekly run, and all of
# it inside the window where the shared lock keeps the nightly dump from running.
# The failure is reported rather than swallowed: a discarded diagnostic in a job
# whose only monitoring channel is its container log leaves nothing to act on.
if ! start_wal="$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -tAc 'SELECT pg_walfile_name(pg_current_wal_lsn());' 2>&1)"; then
  log "could not ask the server for its current WAL segment: $start_wal"
  exit 1
fi
start_wal="$(printf '%s' "$start_wal" | tr -d '[:space:]')"
case "$start_wal" in
  *[!0-9A-F]*) start_wal="" ;;
esac
if [ "${#start_wal}" -ne 24 ]; then
  log "the server did not return a usable WAL segment name; refusing to take a base"
  log "a base published without a replay floor leaves every retained segment prunable"
  exit 1
fi

# --- base backup (PITR-03): temp dir, renamed onto the final name on success ----
# -X stream opens a second replication connection and bundles the WAL generated
# during the copy into the artifact, so the base is internally consistent on its
# own; the archive supplies everything AFTER it. --checkpoint=fast avoids waiting
# out a spread checkpoint on a scheduled run.
log "taking a base backup of $POSTGRES_HOST -> $base"
pg_basebackup -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -D "$tmp" \
  -Ft -z -X stream --checkpoint=fast

# The floor is written INSIDE the temp directory, so the rename below publishes the
# base and the segment its replay starts from atomically — a base can never appear
# without one, which would leave every retained segment prunable.
printf '%s\n' "$start_wal" > "$tmp/START_WAL"
log "base starts at WAL segment $start_wal"

mv "$tmp" "$base"
log "wrote $base"

# --- offsite (PITR-04): only when ALL four remote vars are set ------------------
offsite=0
if [ -n "${LEARNY_BACKUP_REMOTE_ENDPOINT:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_ACCESS_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_SECRET_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_BUCKET:-}" ]; then
  offsite=1
  log "offsite configured; copying the base backup"
  mc alias set learny_offsite "$LEARNY_BACKUP_REMOTE_ENDPOINT" \
    "$LEARNY_BACKUP_REMOTE_ACCESS_KEY" "$LEARNY_BACKUP_REMOTE_SECRET_KEY"
  # Create the offsite bucket if absent (idempotent) so a fresh S3 target works.
  mc mb --ignore-existing "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET"
  mc cp --recursive "$base" "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/base/"
else
  log "offsite not configured"
fi

# --- prune (PITR-06): after a successful backup; newest base always exempt ------
# `set -e` means a failed backup above never reaches this point, so a failure can
# never shrink the retention window.
newest="$(ls -1dt "$LEARNY_BASEBACKUP_DIR"/learny-base-* 2>/dev/null | head -n1)"
find "$LEARNY_BASEBACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name 'learny-base-*' \
  -mtime "+$LEARNY_BACKUP_KEEP_DAYS" ! -path "$newest" -print -exec rm -rf {} +
if [ "$offsite" -eq 1 ]; then
  # The base just uploaded is age 0, so an --older-than KEEP_DAYS window never
  # removes it (offsite newest-exemption).
  mc rm --recursive --force --older-than "${LEARNY_BACKUP_KEEP_DAYS}d" \
    "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/base/"
fi

log "base backup complete"
