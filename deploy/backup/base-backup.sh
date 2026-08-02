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
#     retention derivable from a retained base instead of from age alone
#   * offsite work runs only when ALL four LEARNY_BACKUP_REMOTE_* vars are set;
#     otherwise the run logs "offsite not configured" and still finishes locally
#   * pruning runs only after a successful backup, with the newest base always exempt
# Runs under the image's busybox ash (alpine), which supports `pipefail`.
set -euo pipefail

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=learny}"
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

# --- base backup (PITR-03): temp dir, renamed onto the final name on success ----
# -X stream opens a second replication connection and bundles the WAL generated
# during the copy into the artifact, so the base is internally consistent on its
# own; the archive supplies everything AFTER it. --checkpoint=fast avoids waiting
# out a spread checkpoint on a scheduled run.
log "taking a base backup of $POSTGRES_HOST -> $base"
pg_basebackup -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -D "$tmp" \
  -Ft -z -X stream --checkpoint=fast

# --- record the replay floor (PITR-05's input) ---------------------------------
# backup_label names the first WAL segment a replay from this base needs. Without
# it WAL retention would have nothing to derive from and would fall back to age,
# which is exactly the silent chain-breaking this cycle exists to prevent — so an
# unreadable label fails the run rather than producing a base that cannot pin WAL.
start_wal="$(
  tar -xzOf "$tmp/base.tar.gz" backup_label 2>/dev/null |
    sed -n 's/^START WAL LOCATION: .*(file \([0-9A-F]\{24\}\))$/\1/p'
)"
if [ -z "$start_wal" ]; then
  log "could not read START WAL LOCATION from the base backup label"
  exit 1
fi
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
