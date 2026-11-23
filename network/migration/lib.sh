# shared by the migration scripts. Source it, do not run it.
# Default is dry-run: commands are printed. Nothing changes without --apply.

APPLY=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--apply" ]; then APPLY=1; else ARGS+=("$a"); fi
done

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKUP_ROOT=${BACKUP_ROOT:-/root/migration-backup}
IFACE_FILE=/etc/network/interfaces.d/vmbr2

say() { echo "== $*"; }
die() { echo "error: $*" >&2; exit 1; }

# run a command, or just print it
run() {
  if [ "$APPLY" = 1 ]; then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi
}

# same, but stdout goes to a file: run_to FILE cmd...
run_to() {
  local f=$1; shift
  if [ "$APPLY" = 1 ]; then echo "+ $* > $f"; "$@" > "$f"; else echo "[dry-run] $* > $f"; fi
}

mode() {
  if [ "$APPLY" = 1 ]; then say "APPLY mode: changes are made"; else say "dry-run: nothing is changed (add --apply to run)"; fi
}

# original saved config of a CT: oldest copy that is still on vmbr0 (a retry would save an already changed one)
oldest_ct_conf() {
  local f
  for f in $(ls -1 "$BACKUP_ROOT"/*/ct"$1".conf 2>/dev/null | sort); do
    if grep -q '^net0:.*bridge=vmbr0' "$f"; then echo "$f"; return 0; fi
  done
  return 1
}

zone_for() { # vmid -> vlan
  case $1 in 101) echo 20;; 102) echo 30;; *) return 1;; esac
}
