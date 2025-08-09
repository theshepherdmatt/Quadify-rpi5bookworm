#!/bin/bash
set -Eeuo pipefail
IFS=$'\n\t'
APP_USER="volumio"; APP_GROUP="volumio"
INSTALL_DIR="/home/volumio/Quadify"
TMP_DIR="/home/volumio/Quadify_new"
BAK_DIR="/home/volumio/Quadify_backup_$(date +'%Y%m%d-%H%M%S')"
GIT_URL="https://github.com/theshepherdmatt/Quadify-Beta.git"
GIT_BRANCH="main"
PRESERVE_FILES=("src/preference.json" "config.yaml")
SERVICES=("quadify")
LOG_FILE="/var/log/quadify_update.log"

log(){ echo "[$(date +'%F %T')] $*" | tee -a "$LOG_FILE"; }
ok(){ log "OK: $*"; }
die(){ log "ERROR: $*"; exit 1; }
need_cmd(){ command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }
cleanup_tmp(){ [[ -d "$TMP_DIR" ]] && rm -rf "$TMP_DIR" || true; }
trap cleanup_tmp EXIT

mkdir -p "$(dirname "$LOG_FILE")"; touch "$LOG_FILE" || true
need_cmd git; need_cmd systemctl; need_cmd rsync; need_cmd curl

log "🔄 Starting Quadify update…"
log "Using repo: $GIT_URL (branch: $GIT_BRANCH)"
curl -fsSL --max-time 10 https://api.github.com/rate_limit >/dev/null 2>&1 || die "Network/GitHub unreachable."

for s in "${SERVICES[@]}"; do log "Stopping service: $s"; sudo systemctl stop "$s" || true; done; sleep 1

mkdir -p "$BAK_DIR/preserve"
for rel in "${PRESERVE_FILES[@]}"; do
  src="${INSTALL_DIR}/${rel}"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$BAK_DIR/preserve/$rel")"
    cp -a "$src" "$BAK_DIR/preserve/$rel"
    ok "Backed up ${rel}"
  fi
done

log "Backing up current install to: $BAK_DIR/current"
mkdir -p "$BAK_DIR/current"
rsync -a --delete --exclude ".git" "${INSTALL_DIR}/" "${BAK_DIR}/current/" || die "Backup failed"

log "Fetching latest source into: $TMP_DIR"
rm -rf "$TMP_DIR"
git clone --branch "$GIT_BRANCH" --depth 1 "$GIT_URL" "$TMP_DIR" || die "git clone failed"

log "Deploying new files into: $INSTALL_DIR"
rsync -a --delete "${TMP_DIR}/" "${INSTALL_DIR}/" || die "Deploy failed"

for rel in "${PRESERVE_FILES[@]}"; do
  bak="$BAK_DIR/preserve/$rel"; dest="${INSTALL_DIR}/${rel}"
  if [[ -f "$bak" ]]; then mkdir -p "$(dirname "$dest")"; cp -a "$bak" "$dest"; ok "Restored ${rel}"; fi
done

chown -R "$APP_USER:$APP_GROUP" "$INSTALL_DIR" || true
chmod -R 755 "$INSTALL_DIR" || true

# Write/update a human-readable version stamp (optional but handy for your menu)
echo "$(date +'%Y.%m.%d')-beta" > "$INSTALL_DIR/VERSION" || true

log "Reloading systemd units…"
sudo systemctl daemon-reload || true
for s in "${SERVICES[@]}"; do log "Starting service: $s"; sudo systemctl start "$s" || die "Failed to start $s"; done

for i in {1..15}; do
  if curl -fsS http://localhost:3000/api/v1/getstate | grep -q '"status"'; then ok "Volumio API responsive."; break; fi
  sleep 1
done

ok "✅ Quadify update finished successfully."
exit 0
