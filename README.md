# Quadify-Beta Repository Overview
This is the BETA branch of Quadify
This repository contains the latest features, fixes, and experimental changes before they are merged into the stable Quadify release.
Use this version if you want early access to new features, but understand it may be less stable than the mainline Quadify repository.

Overview
Quadify-Beta is a comprehensive guide and toolkit for integrating Quadify audio hardware enhancements into Raspberry Pi audio systems. Initially developed by Audiophonics, this project has been extensively enhanced by the Quadify team, with all new updates debuting here before stable release.

This repository contains:

All necessary files for hardware integration (OLED, buttons, rotary encoder, LEDs)

Updated install scripts and documentation

Experimental and in-progress features

Supported Systems
For Volumio Users:

OLED display installation

Button and LED integration

Rotary encoder installation

Important Notes (Beta-Specific):
Bleeding Edge:
This version may include features, fixes, or improvements not yet fully tested.
If you need maximum reliability, use the stable Quadify repository.

Intended for new setups but should work for most existing Volumio installs. In rare cases, you might need a system reset.

Back up your data first!

Active internet required for all dependencies.

Standard Volumio settings are preserved (you may still need to use the Volumio WebUI for some sound/volume adjustments).

Quick Start
Clone the Beta repo:

```bash
git clone https://github.com/theshepherdmatt/Quadify-Beta.git
```
* then
```
mv Quadify-Beta Quadify 
```
(this changes the folder/paths to the original Quadify)

* and
```
cd Quadify
sudo bash install.sh
```

(If you prefer HTTPS, use https://github.com/theshepherdmatt/Quadify-Beta.git)

A reboot may be required after install; you’ll be prompted if so.

Installation Timeframe
Installation time varies (OLED: ~5 min on Volumio, longer if compiling from source)

Beta updates may occasionally change this process—watch the repo for new commit notes

Stable Version
For the latest stable and recommended Quadify release, please use:
https://github.com/theshepherdmatt/Quadify

* Post-installation, a system reboot might be necessary to apply the changes effectively. You’ll be informed via command line if such an action is required.

## Installation Timeframe :
Given the diverse landscape of Linux distributions tailored for Raspberry Pi audio setups and their varying update cycles, the installation duration can significantly fluctuate. Direct compilation of certain components from their source is a necessity, affecting overall setup time. For instance, setting up OLED may take approximately 5 minutes on Volumio audio systems.

## Compiling run_update Helper
The install script builds a small setuid wrapper used for automated updates. If you run `install.sh` as root, it will compile `scripts/run_update.c` automatically:

```bash
gcc -o scripts/run_update scripts/run_update.c
chown root:root scripts/run_update
chmod 4755 scripts/run_update
```

This step gives the Volumio user permission to perform updates.

