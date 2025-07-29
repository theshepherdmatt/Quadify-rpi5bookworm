# Quadify

Quadify is a comprehensive toolkit and plugin for integrating advanced audio display and control hardware with your Raspberry Pi audio system. Designed for use with Volumio, Quadify brings new life to classic Quad FM4 tuners and other devices, adding modern features such as OLED displays, rotary encoders, buttons, and LEDs.

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

```
git clone https://github.com/theshepherdmatt/Quadify-Beta.git
mv Quadify-Beta Quadify
cd Quadify
sudo bash install.sh

```

Follow the on-screen prompts. A reboot may be required after installation (you will be notified if so).

## Installation Timeframe

* **Typical install time:** \~5 minutes for OLED on Volumio
  (longer if compiling certain components from source)
* Installation steps may change as the project evolves—check commit notes and documentation for updates.


## Debugging and Service Management

If Quadify isn’t working as expected, try the following steps to identify and resolve common issues:

### 1. Restart Quadify Services

Most issues can be fixed by restarting the relevant services. From the terminal:

```bash
sudo systemctl restart quadify
```

Or to stop and start manually:

```bash
sudo systemctl stop quadify
sudo systemctl start quadify
```

### 2. Manually Run Quadify

For more detailed error messages or debugging, run Quadify directly and watch the logs:

```bash
cd Quadify/src
python3 main.py
```

Check the output for errors—this can help identify configuration or dependency issues.

### 3. Check Quadify Service Logs

To see the system logs for the Quadify service:

```bash
journalctl -u quadify -f
```

This will show live logs. For a broader look, just:

```bash
journalctl -u quadify
```

### 4. Check Volumio Logs

Since Quadify integrates tightly with Volumio, check the main Volumio service logs for related errors:

```bash
journalctl -u volumio -f
```

### 5. Check CAVA Visualiser Service (if using VU Meter)

Some display modes (e.g., the VU Meter) require the CAVA visualiser to be running. To check CAVA’s status:

```bash
sudo systemctl status cava
```

If it’s not active, start it:

```bash
sudo systemctl start cava
```

You can also enable it to start at boot:

```bash
sudo systemctl enable cava
```

---

**If you encounter persistent issues, please open an [Issue](https://github.com/theshepherdmatt/Quadify/issues) with details of your setup and any error messages.**
