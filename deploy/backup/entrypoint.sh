#!/bin/sh
# Backup image entrypoint (RFC-003 Cycle A).
#   * default (no args / "crond"): render the crontab from LEARNY_BACKUP_CRON and
#     run crond in the foreground so job output lands on the container's stdout.
#   * any other command (e.g. `backup-now`, `restore ...`): exec it directly with
#     the container environment (used by on-demand runs and CI).
set -eu

case "${1:-crond}" in
  crond)
    : "${LEARNY_BACKUP_CRON:=30 3 * * *}"
    # Cron jobs run with a bare environment; persist the container's backup-related
    # env (single-quote-escaped, so any secret value survives) so the scheduled
    # backup.sh sees the same config as an on-demand run.
    printenv | while IFS='=' read -r key val; do
      case "$key" in
        POSTGRES_*|MINIO_*|LEARNY_*)
          esc=$(printf '%s' "$val" | sed "s/'/'\\\\''/g")
          printf "export %s='%s'\n" "$key" "$esc"
          ;;
      esac
    done > /etc/backup.env

    printf '%s /usr/local/bin/backup.sh > /proc/1/fd/1 2>/proc/1/fd/2\n' \
      "$LEARNY_BACKUP_CRON" > /etc/crontabs/root
    echo "[entrypoint] scheduled backup at '$LEARNY_BACKUP_CRON'"
    exec crond -f -l 8
    ;;
  *)
    exec "$@"
    ;;
esac
