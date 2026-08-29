#!/bin/sh
# Scheduled WAL segment shipping + retention (RFC-005 Cycle E).
#
# The database archives each completed WAL segment into a volume this sidecar
# shares. The database holds no S3 client and no offsite credential by decision, so
# everything past that volume happens here: copying segments offsite, and deleting
# the ones no retained base backup needs any more.
#
# Contract (spec PITR-04, PITR-05):
#   * its OWN lock -- unlike the base backup, this job neither reads the whole
#     database nor competes with a dump, and it runs every few minutes; sharing the
#     dump's lock would let one nightly dump silently stretch the offsite recovery
#     point. The lock only stops this job overlapping ITSELF on a slow upload.
#   * offsite work runs only when ALL four LEARNY_BACKUP_REMOTE_* vars are set;
#     otherwise the run logs "offsite not configured" and still prunes locally
#   * a segment is deleted only when it is BOTH older than the retention window AND
#     no longer required to replay from the oldest RETAINED base backup. Age alone is
#     never sufficient: pruning by age silently breaks the replay chain of a base
#     that is still inside its window, and the break is invisible until someone
#     actually attempts a restore.
#   * with no retained base backup, NOTHING is pruned -- there is no floor to derive
#     from, and the fail-safe direction is to keep segments
# Runs under the image's busybox ash (alpine), which supports `pipefail`.
set -euo pipefail

# Cron runs jobs with a bare environment; the entrypoint persists the container env here.
[ -f /etc/backup.env ] && . /etc/backup.env

: "${LEARNY_WAL_ARCHIVE_DIR:=/wal_archive}"
: "${LEARNY_BASEBACKUP_DIR:=/backups/base}"
: "${LEARNY_WAL_KEEP_DAYS:=14}"
: "${LEARNY_WAL_LOCK:=/tmp/learny-wal.lock}"

log() { echo "[wal-archive] $*"; }

# --- single-run guard (this job only) ------------------------------------------
exec 9>"$LEARNY_WAL_LOCK"
if ! flock -n 9; then
  log "another WAL shipping run holds the lock; exiting"
  exit 0
fi

if [ ! -d "$LEARNY_WAL_ARCHIVE_DIR" ]; then
  log "archive directory $LEARNY_WAL_ARCHIVE_DIR is absent; nothing to ship"
  exit 0
fi

# --- offsite (PITR-04): only when ALL four remote vars are set ------------------
offsite=0
if [ -n "${LEARNY_BACKUP_REMOTE_ENDPOINT:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_ACCESS_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_SECRET_KEY:-}" ] \
   && [ -n "${LEARNY_BACKUP_REMOTE_BUCKET:-}" ]; then
  offsite=1
  log "offsite configured; shipping newly archived segments"
  mc alias set learny_offsite "$LEARNY_BACKUP_REMOTE_ENDPOINT" \
    "$LEARNY_BACKUP_REMOTE_ACCESS_KEY" "$LEARNY_BACKUP_REMOTE_SECRET_KEY"
  # Create the offsite bucket if absent (idempotent) so a fresh S3 target works.
  mc mb --ignore-existing "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET"
  # Deliberately WITHOUT --overwrite: an archived segment is immutable, so a local
  # file differing from the object of the same name means something is wrong and
  # overwriting would destroy the good copy — the same reason archive_command
  # refuses to overwrite. Shipping happens BEFORE pruning, so a segment can never
  # be deleted locally before it has reached the offsite bucket.
  mc mirror "$LEARNY_WAL_ARCHIVE_DIR" \
    "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/wal"
else
  log "offsite not configured"
fi

# --- the replay floor: what the oldest RETAINED base backup still needs ---------
# Bases are named with a sortable UTC stamp, so the lexically first is the oldest.
# `|| true` is load-bearing: with no base backups at all the glob matches nothing and
# `ls` exits non-zero, which under `set -e`/`pipefail` would abort the whole run
# instead of reaching the no-base branch below — turning the fail-safe into a crash.
oldest_base="$(ls -1d "$LEARNY_BASEBACKUP_DIR"/learny-base-* 2>/dev/null | sort | head -n1 || true)"
if [ -z "$oldest_base" ] || [ ! -f "$oldest_base/START_WAL" ]; then
  log "no retained base backup with a recorded start segment; pruning no segments"
  log "WAL shipping complete"
  exit 0
fi
floor="$(cat "$oldest_base/START_WAL")"
log "oldest retained base ${oldest_base##*/} replays from $floor; nothing below it may be pruned"

# --- prune (PITR-05): older than the window AND below the floor -----------------
candidates="$(mktemp)"
pruned="$(mktemp)"
offsite_present="$(mktemp)"
trap 'rm -f "$candidates" "$pruned" "$offsite_present"' EXIT

# The age condition, applied first. It can only ever WITHHOLD a segment from
# pruning; it is never on its own grounds to delete one.
find "$LEARNY_WAL_ARCHIVE_DIR" -maxdepth 1 -type f \
  -mtime "+$LEARNY_WAL_KEEP_DAYS" -print > "$candidates"

while IFS= read -r path; do
  name="${path##*/}"
  case "$name" in
    # Timeline history files are a few bytes each and are what lets a restore
    # resolve which timeline to follow; they are never pruned.
    *.history) continue ;;
  esac
  # Segment file names are fixed-width hex that sorts in WAL order; a `.backup`
  # label shares its segment's first 24 characters, so one rule covers both.
  segment="$(printf '%.24s' "$name")"
  # STRICTLY below the floor. A segment equal to the floor is the one the oldest
  # base starts replaying from and must survive.
  if [ "$segment" \< "$floor" ]; then
    rm -f "$path"
    printf '%s\n' "$name" >> "$pruned"
  fi
done < "$candidates"

pruned_count="$(wc -l < "$pruned" | tr -d ' ')"
log "pruned $pruned_count segment(s) below $floor"

# Offsite pruning mirrors exactly what was just removed locally — never a bulk
# age sweep and never `mirror --remove`, either of which would let an emptied or
# lost local archive wipe the offsite copy that exists for precisely that case.
#
# One listing plus one batched removal, not two processes per segment. The floor
# only advances when the oldest base is pruned — weekly — so a single run can make
# roughly a week of segments eligible at once (~670 at the default archive_timeout).
# Serialized, that was ~1340 process starts, TLS handshakes and re-authentications
# inside a job scheduled every 15 minutes, with `flock -n` then dropping the runs
# that overlapped and stretching the very offsite recovery point this job maintains.
if [ "$offsite" -eq 1 ] && [ -s "$pruned" ]; then
  # The listing keeps the removal to objects that actually exist: a segment archived
  # before offsite was configured never reached the bucket, and `mc rm` on a missing
  # object would abort the run. `|| true` covers the prefix not existing at all.
  mc ls "learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/wal/" 2>/dev/null \
    | awk '{print $NF}' > "$offsite_present" || true
  targets=""
  while IFS= read -r name; do
    if grep -qxF "$name" "$offsite_present"; then
      targets="$targets learny_offsite/$LEARNY_BACKUP_REMOTE_BUCKET/wal/$name"
    fi
  done < "$pruned"
  if [ -n "$targets" ]; then
    # Deliberately unquoted: the words ARE the object paths, and a WAL segment name
    # is fixed-width hex with no whitespace in it.
    # shellcheck disable=SC2086
    mc rm --force $targets
  fi
fi

log "WAL shipping complete"
