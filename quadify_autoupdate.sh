#!/bin/bash

# 1) Wait a bit to ensure Quadify can fully stop before overwriting
sleep 2

# 2) Stop Quadify
sudo systemctl stop quadify

# 3) Clone fresh code
rm -rf /home/volumio/Quadify_new
git clone https://github.com/theshepherdmatt/Quadify.git /home/volumio/Quadify_new

# 4) Rename old folder, put the new one in place
rm -rf /home/volumio/Quadify_old
mv /home/volumio/Quadify /home/volumio/Quadify_old
mv /home/volumio/Quadify_new /home/volumio/Quadify

# 5) Restart Quadify
sudo systemctl start quadify
