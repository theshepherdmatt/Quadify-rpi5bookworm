#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

echo "🔄 Starting Quadify update..."

# 1) Stop playback and related services
echo "Stopping Quadify and Volumio services..."
sudo systemctl stop quadify
sudo systemctl stop volumio
sleep 2

# 2) Backup preferences
PREF_SRC="/home/volumio/Quadify/src/preference.json"
PREF_BAK="/tmp/preference.json.bak"
if [ -f "$PREF_SRC" ]; then
    echo "Backing up preference.json..."
    cp "$PREF_SRC" "$PREF_BAK"
fi

# 3) Clone latest beta version
echo "Cloning latest Quadify-Beta..."
rm -rf /home/volumio/Quadify_new
git clone https://github.com/theshepherdmatt/Quadify-Beta.git /home/volumio/Quadify_new

# 4) Replace old code
echo "Replacing old Quadify directory..."
mv /home/volumio/Quadify /home/volumio/Quadify_old 2>/dev/null || true
mv /home/volumio/Quadify_new /home/volumio/Quadify

# 5) Restore preferences
if [ -f "$PREF_BAK" ]; then
    echo "Restoring preference.json..."
    mv "$PREF_BAK" "$PREF_SRC"
    chown volumio:volumio "$PREF_SRC"
    chmod 664 "$PREF_SRC"
fi

# 6) Optional cleanup
echo "Cleaning up backup directory..."
rm -rf /home/volumio/Quadify_old

# 7) Restart services
echo "Restarting Volumio and Quadify..."
sudo systemctl start volumio
sleep 5  # Let Volumio settle
sudo systemctl start quadify

echo "✅ Quadify has been updated and restarted successfully."
