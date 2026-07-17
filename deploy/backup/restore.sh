#!/bin/sh
# Manual restore of a `pg_dump -Fc` archive (RFC-003 Cycle A, spec OPS-09).
#
# Usage: restore <archive|--latest> --yes
#   * without --yes: print the plan and exit non-zero (never touches the database)
#   * unknown archive: exit non-zero, listing the available archives
#   * with --yes: `pg_restore --single-transaction --clean --if-exists` the archive
#     into the configured db (single transaction => a partial failure rolls back whole)
set -eu

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=learny}"
: "${POSTGRES_DB:=learny}"
: "${LEARNY_BACKUP_DIR:=/backups/db}"

usage() { echo "usage: restore <archive|--latest> --yes" >&2; }

list_archives() {
  echo "available archives in $LEARNY_BACKUP_DIR:" >&2
  ls -1 "$LEARNY_BACKUP_DIR"/learny-*.dump 2>/dev/null >&2 || echo "  (none)" >&2
}

spec=""
confirm=0
for arg in "$@"; do
  case "$arg" in
    --yes) confirm=1 ;;
    --latest) spec="--latest" ;;
    --*) echo "unknown option: $arg" >&2; usage; exit 2 ;;
    *) spec="$arg" ;;
  esac
done

if [ -z "$spec" ]; then
  usage
  exit 2
fi

# Resolve the archive first, so an unknown archive exits non-zero listing the
# available ones (OPS-09 edge) regardless of --yes.
if [ "$spec" = "--latest" ]; then
  archive="$(ls -1t "$LEARNY_BACKUP_DIR"/learny-*.dump 2>/dev/null | head -n1)"
  if [ -z "$archive" ]; then
    echo "no archives found" >&2
    list_archives
    exit 1
  fi
else
  case "$spec" in
    /*) archive="$spec" ;;
    *) archive="$LEARNY_BACKUP_DIR/$spec" ;;
  esac
  if [ ! -f "$archive" ]; then
    echo "archive not found: $spec" >&2
    list_archives
    exit 1
  fi
fi

# Without --yes, print the plan and refuse to touch the database (OPS-09).
if [ "$confirm" -ne 1 ]; then
  echo "PLAN: pg_restore --single-transaction --clean --if-exists '$archive' into database '$POSTGRES_DB' on host '$POSTGRES_HOST'"
  echo "re-run with --yes to execute (nothing was changed)"
  exit 1
fi

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
echo "[restore] restoring $archive into $POSTGRES_DB@$POSTGRES_HOST"
# --single-transaction makes the restore all-or-nothing (it implies --exit-on-error),
# so a partial failure rolls back instead of exiting 0 on a half-restored database.
pg_restore --single-transaction --clean --if-exists --no-owner \
  -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$archive"
echo "[restore] restore complete"
