#!/bin/sh
# Point-in-time restore (RFC-005 Cycle E).
#
# Rebuilds a data directory from a physical base backup and configures PostgreSQL
# to replay archived WAL onto it up to a chosen moment. The database container
# holds no object-store client and no offsite credential by decision, so the
# archive-reading half of a restore lives here in the sidecar; the replay itself is
# performed by the profile-gated `db-restore` service, which runs the SAME image as
# `db` and therefore has the same binaries and extensions the cluster was written
# with. Replaying a pgvector cluster with a server that lacks pgvector would start
# and then fail the moment anyone read a vector column.
#
# Usage: restore-pitr.sh --target '<UTC timestamp>' [--yes]
#   * without --yes: resolve everything, print the plan, exit non-zero, and touch
#     nothing on disk
#   * target older than every retained base: exit non-zero naming the earliest
#     recoverable time, before anything is written
#   * with --yes: unpack the newest base that PRECEDES the target, point
#     restore_command at the archive, and set the recovery target
#
# Contract (spec PITR-07, PITR-08):
#   * the target must carry an explicit UTC offset. `recovery_target_time` is read
#     in the SERVER's timezone when the timestamp has none, so a bare timestamp
#     means different moments in different deployments — which makes the boundary
#     of a point-in-time recovery meaningless. Rejecting it is the only honest
#     option available without a timezone database in this image.
#   * the chosen base must START BEFORE the target. A base taken after the target
#     has no path to it: replay only moves forward, so recovery would run out of
#     WAL and PostgreSQL would refuse to finish ("recovery ended before configured
#     recovery target was reached") — a loud failure, but one this script must not
#     walk into on purpose.
#   * PostgreSQL 12 and later drive recovery from `recovery.signal` plus ordinary
#     configuration settings. The pre-12 `recovery.conf` is not read at all and
#     would be silently ignored, leaving a server that starts, replays the whole
#     archive, and looks like a successful restore.
#   * recovery_target_action=promote, so a completed restore leaves a normally
#     running, WRITABLE database. The default (pause) would leave a server that
#     answers reads and refuses writes — indistinguishable from success at a glance.
# Runs under the image's busybox ash (alpine), which supports `pipefail`.
set -euo pipefail

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${LEARNY_BASEBACKUP_DIR:=/backups/base}"
: "${LEARNY_WAL_ARCHIVE_DIR:=/wal_archive}"
: "${LEARNY_PITR_DIR:=/pitr}"

# Deliberately NOT the live data volume. A sidecar that runs cron jobs around the
# clock must not be able to overwrite the database it exists to protect; the
# recovered cluster is staged here and served by `db-restore`.
data_dir="$LEARNY_PITR_DIR/data"

log() { echo "[restore-pitr] $*"; }

usage() {
  echo "usage: restore-pitr.sh --target '<YYYY-MM-DD HH:MM:SS+00:00>' --yes" >&2
  echo "       the target must be expressed in UTC ('Z', '+00' or '+00:00')" >&2
}

# learny-base-2026-08-02-120000 -> 20260802120000 (fixed width, so lexical order IS
# chronological order and a string compare is a time compare).
base_stamp() {
  name="${1##*/}"
  printf '%s' "${name#learny-base-}" | tr -d '-'
}

# 20260802120000 -> 2026-08-02 12:00:00+00:00
pretty_utc() {
  printf '%s-%s-%s %s:%s:%s+00:00' \
    "$(printf '%s' "$1" | cut -c1-4)" \
    "$(printf '%s' "$1" | cut -c5-6)" \
    "$(printf '%s' "$1" | cut -c7-8)" \
    "$(printf '%s' "$1" | cut -c9-10)" \
    "$(printf '%s' "$1" | cut -c11-12)" \
    "$(printf '%s' "$1" | cut -c13-14)"
}

# --- arguments ------------------------------------------------------------------
target=""
confirm=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes) confirm=1 ;;
    --target)
      shift
      if [ "$#" -eq 0 ]; then
        echo "--target needs a timestamp" >&2
        usage
        exit 2
      fi
      target="$1"
      ;;
    --target=*) target="${1#--target=}" ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [ -z "$target" ]; then
  usage
  exit 2
fi

# --- the target must be unambiguous, and it must be UTC -------------------------
case "$target" in
  *Z) naive="${target%Z}" ;;
  *+00:00) naive="${target%+00:00}" ;;
  *+00) naive="${target%+00}" ;;
  *)
    echo "target carries no UTC offset: $target" >&2
    echo "express it in UTC, e.g. '2026-08-02 12:00:00+00:00' (psql: SELECT now() AT TIME ZONE 'UTC')" >&2
    exit 2
    ;;
esac

case "$naive" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][\ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]) ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][\ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9]*) ;;
  *)
    echo "target is not a timestamp: $target" >&2
    usage
    exit 2
    ;;
esac
# Sub-second precision is kept in the value handed to PostgreSQL and dropped only
# from the comparison stamp, which is whole-second by construction.
target_stamp="$(printf '%s' "$naive" | tr -dc '0-9' | cut -c1-14)"

# --- there must be an archive to replay ----------------------------------------
if [ ! -d "$LEARNY_WAL_ARCHIVE_DIR" ]; then
  log "WAL archive directory $LEARNY_WAL_ARCHIVE_DIR is absent; there is nothing to replay"
  exit 1
fi

# --- choose the base backup (PITR-07, PITR-08) ----------------------------------
# Glob expansion is sorted, and the stamps are fixed width, so this walks the bases
# oldest-first; the last one that does not start after the target is the newest one
# that can reach it.
oldest=""
chosen=""
for candidate in "$LEARNY_BASEBACKUP_DIR"/learny-base-*; do
  # An incomplete directory (a crashed run's leftovers) is not a base backup.
  [ -f "$candidate/base.tar.gz" ] || continue
  # The FIRST complete base the sorted glob yields is the oldest retained one, and
  # its start is the floor of the whole recoverable window: WAL retention is derived
  # from exactly this base, so nothing below it survives to be replayed.
  [ -n "$oldest" ] || oldest="$candidate"
  if [ "$(base_stamp "$candidate")" \> "$target_stamp" ]; then
    continue
  fi
  chosen="$candidate"
done

if [ -z "$oldest" ]; then
  log "no base backup in $LEARNY_BASEBACKUP_DIR"
  log "archived WAL is not a recovery chain on its own; there is nothing to replay onto"
  log "nothing was changed"
  exit 1
fi

# --- a target below the window fails loudly, and says how far back it goes -------
# "Out of range" without a range is an error an operator can only resolve by reading
# the source; naming the floor turns a dead end into the next thing to try.
if [ -z "$chosen" ]; then
  log "target $target is outside the recoverable window"
  log "earliest recoverable time: $(pretty_utc "$(base_stamp "$oldest")") (oldest retained base ${oldest##*/})"
  log "nothing was changed"
  exit 1
fi

chosen_at="$(pretty_utc "$(base_stamp "$chosen")")"

# --- without --yes, print the plan and refuse to touch anything (PITR-07) -------
# Placed AFTER resolution so an out-of-window target fails identically with and
# without --yes, and BEFORE the first write so the dry run is inert rather than
# merely stopping short of the last step.
if [ "$confirm" -ne 1 ]; then
  echo "PLAN: restore base ${chosen##*/} (starts $chosen_at) into $data_dir,"
  echo "      replay WAL from $LEARNY_WAL_ARCHIVE_DIR up to '$target',"
  echo "      then serve it with: docker compose --profile restore up -d --wait db-restore"
  echo "re-run with --yes to execute (nothing was changed)"
  exit 1
fi

# --- restore --------------------------------------------------------------------
log "restoring ${chosen##*/} (starts $chosen_at) into $data_dir"
# The staging directory belongs to this script alone; --yes is the confirmation
# that its previous contents may go.
rm -rf "$data_dir"
mkdir -p "$data_dir"
chmod 700 "$data_dir"
tar -xzf "$chosen/base.tar.gz" -C "$data_dir"
# -X stream bundles the WAL written DURING the base backup; without it the cluster
# is not even internally consistent, let alone able to reach a later target.
if [ -f "$chosen/pg_wal.tar.gz" ]; then
  mkdir -p "$data_dir/pg_wal"
  tar -xzf "$chosen/pg_wal.tar.gz" -C "$data_dir/pg_wal"
fi

# --- configure the replay (PostgreSQL 12+ mechanism) ----------------------------
{
  echo ""
  echo "# --- point-in-time recovery (written by restore-pitr.sh) ---"
  echo "restore_command = 'cp \"$LEARNY_WAL_ARCHIVE_DIR/%f\" \"%p\"'"
  echo "recovery_target_time = '$target'"
  echo "recovery_target_action = 'promote'"
} >> "$data_dir/postgresql.auto.conf"
# The file whose PRESENCE puts the server into archive recovery. Without it the
# settings above are inert and the server simply starts on the base backup.
touch "$data_dir/recovery.signal"

log "target $target; the server will promote to a writable database on reaching it"
log "bring it up with: docker compose --profile restore up -d --wait db-restore"
log "restore prepared"
