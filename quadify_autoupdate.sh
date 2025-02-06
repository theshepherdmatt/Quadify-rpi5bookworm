#!/bin/bash

# 1) Wait a bit to ensure Quadify can fully stop before overwriting
sleep 2

# 2) Stop Quadify
sudo systemctl stop quadify

# 3) Copy preference.json to a safe location (if it exists)
if [ -f /home/volumio/Quadify/src/preference.json ]; then
    echo "Backing up preference.json..."
    cp /home/volumio/Quadify/src/preference.json /tmp/preference.json.bak
fi

# 4) Clone fresh code
rm -rf /home/volumio/Quadify_new
git clone https://github.com/theshepherdmatt/Quadify.git /home/volumio/Quadify_new

# 5) Rename old folder & put the new one in place
mv /home/volumio/Quadify /home/volumio/Quadify_old 2>/dev/null
mv /home/volumio/Quadify_new /home/volumio/Quadify

# 6) Restore preference.json if we backed it up
if [ -f /tmp/preference.json.bak ]; then
    echo "Restoring preference.json..."
    cp /tmp/preference.json.bak /home/volumio/Quadify/src/preference.json
    rm /tmp/preference.json.bak

    # Fix ownership so 'volumio' can still write to it
    chown volumio:volumio /home/volumio/Quadify/src/preference.json
    chmod 664 /home/volumio/Quadify/src/preference.json
fi

# 7) Remove old folder (optional: only if you don’t need a backup)
rm -rf /home/volumio/Quadify_old

# 8) Reboot the system
echo "Rebooting the system..."
sudo reboot
