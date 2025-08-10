#!/bin/bash
set -Eeuo pipefail
APP_DIR="/home/volumio/Quadify"
LATEST="$(ls -1dt /home/volumio/Quadify_backup_* 2>/dev/null | head -n1 || true)"
[[ -z "$LATEST" ]] && { echo "No backups found."; exit 1; }
echo "Restoring from: $LATEST"
sudo systemctl stop quadify || true
rsync -a --delete "${LATEST}/current/" "${APP_DIR}/"
chown -R volumio:volumio "$APP_DIR" || true
chmod -R 755 "$APP_DIR" || true
sudo systemctl daemon-reload || true
sudo systemctl start quadify || true
echo "Rollback complete."
