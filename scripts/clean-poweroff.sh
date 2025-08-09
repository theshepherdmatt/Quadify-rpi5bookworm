#!/bin/bash
set -euo pipefail
log(){ logger -t clean-poweroff "$*"; }
log "Starting clean poweroff"

# Stop your extras first so nothing fights the expander
systemctl stop quadify.service early_led8.service ir_listener.service cava.service 2>/dev/null || true

# Force LEDs off
/usr/bin/python3 /usr/local/bin/quadify-leds-off.py || true

# Ask Volumio politely to stop playback
curl -m 2 -s 'http://localhost:3000/api/v1/commands/?cmd=stop' >/dev/null 2>&1 || true
sleep 1

# Core audio/Volumio bits (skip if not present)
systemctl stop volspotconnect2 2>/dev/null || true
systemctl stop shairport-sync 2>/dev/null || true
systemctl stop upmpdcli 2>/dev/null || true
systemctl stop mpd 2>/dev/null || true
systemctl stop volumio 2>/dev/null || true

# Unmount NAS/USB quickly to avoid CIFS/NFS hangs
for m in /mnt/NAS/* /mnt/USB/*; do
  [ -e "$m" ] && umount -l "$m" 2>/dev/null || true
done

sync
log "Clean poweroff finished"
