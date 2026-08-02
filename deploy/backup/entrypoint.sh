#!/bin/sh
# Backup image entrypoint (RFC-003 Cycle A; base backups + WAL shipping added in
# RFC-005 Cycle E).
#   * default (no args / "crond"): render the crontab from the three schedules and
#     run crond in the foreground so job output lands on the container's stdout.
#   * any other command (e.g. `backup-now`, `restore ...`): exec it directly with
#     the container environment (used by on-demand runs and CI).
set -eu

case "${1:-crond}" in
  crond)
    : "${LEARNY_BACKUP_CRON:=30 3 * * *}"
    # Weekly, and deliberately 90 minutes clear of the nightly dump: the two jobs
    # share a lock, so an overlapping base backup would be skipped for that week.
    : "${LEARNY_BASEBACKUP_CRON:=0 2 * * 0}"
    # Cron jobs run with a bare environment; persist the container's backup-related
    # env (single-quote-escaped, so any secret value survives) so the scheduled
    # backup.sh sees the same config as an on-demand run. The snapshot holds DB,
    # MinIO, and offsite credentials, so create it owner-only (umask 077, restored
    # after so the crontab write below keeps its normal mode).
    prev_umask=$(umask)
    umask 077
    printenv | while IFS='=' read -r key val; do
      case "$key" in
        POSTGRES_*|MINIO_*|LEARNY_*)
          esc=$(printf '%s' "$val" | sed "s/'/'\\\\''/g")
          printf "export %s='%s'\n" "$key" "$esc"
          ;;
      esac
    done > /etc/backup.env
    umask "$prev_umask"

    {
      printf '%s /usr/local/bin/backup.sh > /proc/1/fd/1 2>/proc/1/fd/2\n' \
        "$LEARNY_BACKUP_CRON"
      printf '%s /usr/local/bin/base-backup.sh > /proc/1/fd/1 2>/proc/1/fd/2\n' \
        "$LEARNY_BASEBACKUP_CRON"
    } > /etc/crontabs/root
    echo "[entrypoint] scheduled backup at '$LEARNY_BACKUP_CRON'"
    echo "[entrypoint] scheduled base backup at '$LEARNY_BASEBACKUP_CRON'"
    exec crond -f -l 8
    ;;
  *)
    exec "$@"
    ;;
esac
