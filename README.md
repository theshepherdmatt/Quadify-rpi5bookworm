# Quadify

Quadify is a comprehensive toolkit and plugin for integrating advanced audio display and control hardware with your Raspberry Pi audio system. Designed for use with Volumio, Quadify brings new life to classic Quad FM4 tuners and other devices—adding modern features such as OLED displays, rotary encoders, buttons, and LEDs.

## Overview

Originally inspired by work from Audiophonics, Quadify has been extensively enhanced by the open-source community.
This repository contains everything you need to add display, button, and rotary encoder support to your Pi-based audio system.

**Features:**

* OLED display integration (various types supported)
* Button and LED input/output
* Rotary encoder support
* Modular hardware configuration
* Easy install scripts and update mechanism

## Supported Systems

Quadify is designed and tested for **Volumio** (Raspberry Pi OS).
Other Pi-based audio distributions may work, but are not officially supported.

Supported features include:

* OLED display installation
* Button and LED integration
* Rotary encoder installation

## Important Notes

* **Stable Release:** This is the main Quadify repository. For the latest features or experimental work, check for a `beta` branch.
* **Intended for new setups**, but should work for existing Volumio installs.
* **Back up your data first!**
* An **active internet connection** is required for installation (to fetch dependencies).
* Standard Volumio settings are preserved, but you may need to use the Volumio Web UI for some system or audio settings.

## Quick Start

Clone this repository:

```bash
git clone https://github.com/theshepherdmatt/Quadify.git
cd Quadify
sudo bash install.sh
```

Follow the on-screen prompts. A reboot may be required after installation (you will be notified if so).

## Installation Timeframe

* **Typical install time:** \~5 minutes for OLED on Volumio
  (longer if compiling certain components from source)
* Installation steps may change as the project evolves—check commit notes and documentation for updates.

## Compiling `run_update` Helper

The install script automatically builds a small setuid wrapper (`scripts/run_update.c`) to allow the Volumio user to perform updates:

```bash
gcc -o scripts/run_update scripts/run_update.c
chown root:root scripts/run_update
chmod 4755 scripts/run_update
```

This step is handled by the installer if you run `install.sh` as root (recommended).

## Troubleshooting & Feedback

If you encounter issues, please check the [Issues](https://github.com/theshepherdmatt/Quadify/issues) tab and join the discussion.
