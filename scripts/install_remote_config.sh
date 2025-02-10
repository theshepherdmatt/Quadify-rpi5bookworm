#!/bin/bash

echo "DEBUG: Effective UID is: $(id -u)"
echo "DEBUG: Script path is: $(readlink -f "$0")"
if [ "$EUID" -ne 0 ]; then
    echo "Not running as root, re-launching with sudo..."
    exec sudo /home/volumio/Quadify/scripts/install_remote_config.sh "$@"
fi

REMOTE_FOLDER="$1"
SOURCE_DIR="/home/volumio/Quadify/lirc/configurations/$REMOTE_FOLDER/"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Directory '$SOURCE_DIR' does not exist."
    exit 1
fi

SOURCE_LIRCD="${SOURCE_DIR}lircd.conf"
SOURCE_LIRCRC="${SOURCE_DIR}lircrc"

if [ ! -f "$SOURCE_LIRCD" ]; then
    echo "Error: File '$SOURCE_LIRCD' not found."
    exit 1
fi

if [ ! -f "$SOURCE_LIRCRC" ]; then
    echo "Error: File '$SOURCE_LIRCRC' not found."
    exit 1
fi

cp "$SOURCE_LIRCD" /etc/lirc/lircd.conf || { echo "Error copying lircd.conf"; exit 1; }
cp "$SOURCE_LIRCRC" /etc/lirc/lircrc || { echo "Error copying lircrc"; exit 1; }

systemctl restart lircd || { echo "Error restarting lircd service"; exit 1; }
systemctl restart ir_listener.service || { echo "Error restarting ir_listener.service"; exit 1; }

echo "IR remote configuration installed successfully."
echo "IR remote selected, rebooting in 10 seconds..."
sleep 10
reboot
