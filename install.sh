#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status
#set -x  # Uncomment to enable debugging

# ============================
#   Colour Code Definitions
# ============================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# ============================
#   Variables for Progress Tracking
# ============================
TOTAL_STEPS=17
CURRENT_STEP=0
LOG_FILE="install.log"

# Remove existing log file at start
rm -f "$LOG_FILE"

# ============================
#   ASCII Art Banner Function
# ============================
banner() {
    echo -e "${MAGENTA}"
    echo "======================================================================================================"
    echo "   Quadify Installer: Bringing you a Volumio-based audio experience with custom UI, buttons, and LEDs"
    echo "======================================================================================================"
    echo -e "${NC}"
}

# ============================
#   Log + Progress Functions
# ============================
log_message() {
    local type="$1"
    local message="$2"
    case "$type" in
        "info")    echo -e "${BLUE}[INFO]${NC} $message" ;;
        "success") echo -e "${GREEN}[SUCCESS]${NC} $message" ;;
        "warning") echo -e "${YELLOW}[WARNING]${NC} $message" ;;
        "error")   echo -e "${RED}[ERROR]${NC} $message" >&2 ;;
    esac
}

log_progress() {
    local message="$1"
    CURRENT_STEP=$((CURRENT_STEP + 1))
    echo -e "${BLUE}[${CURRENT_STEP}/${TOTAL_STEPS}]${NC} $message"
}

# ============================
#  Check Root BEFORE We Call It
# ============================
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_message "error" "Please run as root or via sudo."
        exit 1
    fi
}

# ============================
#   Quadify-Specific Tips
# ============================
TIPS=(
  "Long-press any button to return home to the clock mode."
  "Under 'Config', you can switch display modes—Modern, Original, or Minimal-Screen."
  "Don’t forget to explore different screensaver types under 'Screensaver' in Config!"
  "Brightness can be tweaked in Config -> Display for late-night listening."
  "Quadify: Where code meets Hi-Fi. Check new clock faces in 'Clock' menu!"
  "Need track info? Modern screen overlays sample rate & bit depth at the bottom."
  "Help & logs: see install.log or run 'journalctl -u quadify.service'."
  "Idle logic is improved—no more burnt-in OLED pixels!"
)

show_random_tip() {
    local index=$((RANDOM % ${#TIPS[@]}))
    log_message "info" "Tip: ${TIPS[$index]}"
}

# ============================
#   run_command with Minimal Output
# ============================
run_command() {
    local cmd="$1"
    echo "Running: $cmd" >> "$LOG_FILE"

    echo -e "${MAGENTA}Running command...${NC}"
    bash -c "$cmd" >> "$LOG_FILE" 2>&1
    local exit_status=$?
    if [ $exit_status -ne 0 ]; then
        log_message "error" "Command failed: $cmd. Check $LOG_FILE for details."
        exit 1
    fi
    echo -e "${GREEN}Done.${NC}"
}

# ============================
#   Start Script with Banner
# ============================
banner

# ============================
#   System Dependencies
# ============================
install_system_dependencies() {
    log_progress "Installing system-level dependencies, this might take a while so put the kettle on..."

    run_command "apt-get update"
    run_command "apt-get install -y \
        python3.7 \
        python3.7-dev \
        python3-pip \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype6-dev \
        i2c-tools \
        python3-smbus \
        libgirepository1.0-dev \
        pkg-config \
        libcairo2-dev \
        libffi-dev \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libssl-dev \
        lsof"

    log_message "success" "System-level dependencies installed. (ᵔᴥᵔ)"
    show_random_tip
}

upgrade_pip() {
    log_progress "Upgrading pip, setuptools, and wheel..."
    run_command "python3.7 -m pip install --upgrade pip setuptools wheel"
    log_message "success" "pip, setuptools, and wheel upgraded."
    show_random_tip
}

install_python_dependencies() {
    log_progress "Installing Python dependencies, please wait..."

    # Force-install pycairo first
    run_command "python3.7 -m pip install --upgrade --ignore-installed pycairo"

    # Then the rest from requirements.txt
    run_command "python3.7 -m pip install --upgrade --ignore-installed -r /home/volumio/Quadify/requirements.txt"
    log_message "success" "Python dependencies installed. (•‿•)"
    show_random_tip
}

enable_i2c_spi() {
    log_progress "Enabling I2C and SPI in config.txt..."

    CONFIG_FILE="/boot/userconfig.txt"
    if [ ! -f "$CONFIG_FILE" ]; then
        run_command "touch \"$CONFIG_FILE\""
    fi

    # SPI
    if ! grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
        echo "dtparam=spi=on" >> "$CONFIG_FILE"
        log_message "success" "SPI enabled in userconfig.txt."
    else
        log_message "info" "SPI is already enabled."
    fi

    # I2C
    if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE"; then
        echo "dtparam=i2c_arm=on" >> "$CONFIG_FILE"
        log_message "success" "I2C enabled in userconfig.txt."
    else
        log_message "info" "I2C is already enabled."
    fi

    log_progress "Loading I2C and SPI kernel modules..."
    run_command "modprobe i2c-dev"
    run_command "modprobe spi-bcm2835"

    if [ -e /dev/i2c-1 ]; then
        log_message "success" "/dev/i2c-1 is present."
    else
        log_message "warning" "/dev/i2c-1 not found; trying modprobe i2c-bcm2708..."
        run_command "modprobe i2c-bcm2708"
        sleep 1
        if [ -e /dev/i2c-1 ]; then
            log_message "success" "/dev/i2c-1 was successfully initialized."
        else
            log_message "error" "Could not initialize /dev/i2c-1. Check config and wiring."
            exit 1
        fi
    fi
    show_random_tip
}

# ============================
#   Detect/Set MCP23017 Address
# ============================
detect_i2c_address() {
    log_progress "Detecting MCP23017 I2C address..."

    i2c_output=$(/usr/sbin/i2cdetect -y 1)
    echo "$i2c_output" >> "$LOG_FILE"
    echo "$i2c_output"

    address=$(echo "$i2c_output" | grep -oE '\b(20|21|22|23|24|25|26|27)\b' | head -n 1)

    if [[ -z "$address" ]]; then
        log_message "warning" "No MCP23017 detected. Check wiring."
    else
        log_message "success" "MCP23017 found at I2C: 0x$address."
        update_buttonsleds_address "$address"
    fi
    show_random_tip
}

update_buttonsleds_address() {
    local detected_address="$1"
    BUTTONSLEDS_FILE="/home/volumio/Quadify/src/hardware/buttonsleds.py"

    if [[ -f "$BUTTONSLEDS_FILE" ]]; then
        if grep -q "mcp23017_address" "$BUTTONSLEDS_FILE"; then
            run_command "sed -i \"s/mcp23017_address = 0x[0-9a-fA-F]\\{2\\}/mcp23017_address = 0x$detected_address/\" \"$BUTTONSLEDS_FILE\""
            log_message "success" "Updated MCP23017 address in $BUTTONSLEDS_FILE => 0x$detected_address."
        else
            run_command "echo \"mcp23017_address = 0x$detected_address\" >> \"$BUTTONSLEDS_FILE\""
            log_message "success" "Added MCP23017 address line to $BUTTONSLEDS_FILE => 0x$detected_address."
        fi
    else
        log_message "error" "buttonsleds.py not found at $BUTTONSLEDS_FILE."
        exit 1
    fi
}

# ============================
#   Samba Setup
# ============================
setup_samba() {
    log_progress "Configuring Samba for Quadify..."

    SMB_CONF="/etc/samba/smb.conf"
    if [ ! -f "$SMB_CONF.bak" ]; then
        run_command "cp $SMB_CONF $SMB_CONF.bak"
        log_message "info" "Backup of $SMB_CONF created."
    fi

    if ! grep -q "\[Quadify\]" "$SMB_CONF"; then
        cat <<EOF >> "$SMB_CONF"

[Quadify]
   path = /home/volumio/Quadify
   writable = yes
   browseable = yes
   guest ok = yes
   force user = volumio
   create mask = 0777
   directory mask = 0777
   public = yes
EOF
        log_message "success" "Samba config for Quadify appended."
    else
        log_message "info" "Quadify section already in smb.conf."
    fi

    run_command "systemctl restart smbd"
    log_message "success" "Samba restarted."

    run_command "chown -R volumio:volumio /home/volumio/Quadify"
    run_command "chmod -R 777 /home/volumio/Quadify"
    log_message "success" "Permissions set for /home/volumio/Quadify."
    show_random_tip
}

# ============================
#   Main Quadify Service
# ============================
setup_main_service() {
    log_progress "Setting up Main Quadify Service..."

    SERVICE_FILE="/etc/systemd/system/quadify.service"
    LOCAL_SERVICE="/home/volumio/Quadify/service/quadify.service"

    if [[ -f "$LOCAL_SERVICE" ]]; then
        run_command "cp \"$LOCAL_SERVICE\" \"$SERVICE_FILE\""
        run_command "systemctl daemon-reload"
        run_command "systemctl enable quadify.service"
        run_command "systemctl start quadify.service"
        log_message "success" "quadify.service installed and started. (ノ^_^)ノ"
    else
        log_message "error" "quadify.service not found in /home/volumio/Quadify/service."
        exit 1
    fi
    show_random_tip
}

# ============================
#   MPD Configuration
# ============================
configure_mpd() {
    log_progress "Configuring MPD for FIFO..."

    MPD_CONF_FILE="/volumio/app/plugins/music_service/mpd/mpd.conf.tmpl"
    FIFO_OUTPUT="
audio_output {
    type            \"fifo\"
    name            \"my_fifo\"
    path            \"/tmp/cava.fifo\"
    format          \"44100:16:2\"
}"

    if grep -q "/tmp/cava.fifo" "$MPD_CONF_FILE"; then
        log_message "info" "FIFO output config already in MPD conf."
    else
        echo "$FIFO_OUTPUT" | tee -a "$MPD_CONF_FILE" >> "$LOG_FILE"
        log_message "success" "Added FIFO output to MPD conf."
    fi

    run_command "systemctl restart mpd"
    log_message "success" "MPD restarted with updated FIFO config."
    show_random_tip
}

# ============================
#   CAVA Installation
# ============================
check_cava_installed() {
    if command -v cava >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

install_cava_from_fork() {
    log_progress "Installing CAVA from the fork..."

    CAVA_REPO="https://github.com/theshepherdmatt/cava.git"
    CAVA_INSTALL_DIR="/home/volumio/cava"

    if check_cava_installed; then
        log_message "info" "CAVA already installed. Skipping."
        return
    fi

    # Dependencies
    log_message "info" "Installing build dependencies for CAVA..."
    run_command "apt-get install -y \
        libfftw3-dev \
        libasound2-dev \
        libncursesw5-dev \
        libpulse-dev \
        libtool \
        automake \
        autoconf \
        gcc \
        make \
        pkg-config \
        libiniparser-dev"

    if [[ ! -d "$CAVA_INSTALL_DIR" ]]; then
        run_command "git clone $CAVA_REPO $CAVA_INSTALL_DIR"
    else
        run_command "cd $CAVA_INSTALL_DIR && git pull"
    fi

    run_command "cd $CAVA_INSTALL_DIR && ./autogen.sh"
    run_command "cd $CAVA_INSTALL_DIR && ./configure"
    run_command "cd $CAVA_INSTALL_DIR && make"
    run_command "cd $CAVA_INSTALL_DIR && make install"
    log_message "success" "CAVA installed from fork."
    show_random_tip
}

setup_cava_service() {
    log_progress "Setting up CAVA service..."

    CAVA_SERVICE_FILE="/etc/systemd/system/cava.service"
    LOCAL_CAVA_SERVICE="/home/volumio/Quadify/service/cava.service"

    if [[ -f "$LOCAL_CAVA_SERVICE" ]]; then
        run_command "cp \"$LOCAL_CAVA_SERVICE\" \"$CAVA_SERVICE_FILE\""
        run_command "systemctl daemon-reload"
        run_command "systemctl enable cava.service"
        # run_command "systemctl start cava.service"  # Optionally start here
        log_message "success" "CAVA service installed."
    else
        log_message "error" "cava.service not found in /home/volumio/Quadify/service."
    fi
    show_random_tip
}


# ============================
#   Buttons + LEDs Handling
# ============================
configure_buttons_leds() {
    # If user doesn't want buttons/LEDs, we just comment them out
    # If user wants them, we do detection + uncomment

    MAIN_PY_PATH="/home/volumio/Quadify/src/main.py"
    if [[ ! -f "$MAIN_PY_PATH" ]]; then
        log_message "error" "Could not find main.py at $MAIN_PY_PATH."
        exit 1
    fi

    if [ "$BUTTONSLEDS_ENABLED" = false ]; then
        log_message "info" "Disabling 'buttons_leds' usage in main.py..."
        # Comment out lines in main.py:
        if grep -qE "^[^#]*\s*buttons_leds\s*=\s*ButtonsLEDController" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
        fi
        if grep -qE "^[^#]*\s*buttons_leds.start()" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds.start()/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
        fi
        log_message "success" "Buttons/LEDs lines commented out."
    else
        log_message "info" "Enabling 'buttons_leds' usage in main.py..."
        # Uncomment lines in main.py:
        if grep -qE "^[#]*\s*buttons_leds\s*=\s*ButtonsLEDController" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^#//' "$MAIN_PY_PATH"
        fi
        if grep -qE "^[#]*\s*buttons_leds.start()" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds.start()/ s/^#//' "$MAIN_PY_PATH"
        fi
        log_message "success" "Buttons/LEDs lines uncommented."
    fi
}

# ============================
#   Permissions
# ============================
set_permissions() {
    log_progress "Setting ownership & permissions for /home/volumio/Quadify..."
    run_command "chown -R volumio:volumio /home/volumio/Quadify"
    run_command "chmod -R 755 /home/volumio/Quadify"
    log_message "success" "Ownership/permissions set."
}

# ============================
#   Main Installation
# ============================
main() {
    check_root

    log_message "info" "Starting Quadify Installer..."

    # 1) Ask user about Buttons & LEDs with MCP23017
    BUTTONSLEDS_ENABLED=false
    while true; do
        read -rp "Enable Buttons & LEDs with MCP23017? (y/n): " answer
        case $answer in
            [Yy]* )
                BUTTONSLEDS_ENABLED=true
                break
                ;;
            [Nn]* )
                BUTTONSLEDS_ENABLED=false
                break
                ;;
            * )
                log_message "warning" "Please answer y or n."
                ;;
        esac
    done

    # 2) Install system dependencies (includes i2c-tools, etc.)
    install_system_dependencies
    # 3) Enable i2c/spi (only truly needed if using Buttons/LEDs, but safe to keep)
    enable_i2c_spi
    # 4) Upgrade pip
    upgrade_pip
    # 5) Install python dependencies
    install_python_dependencies

    # 6) If user chose Buttons/LEDs, detect I2C address
    if [ "$BUTTONSLEDS_ENABLED" = true ]; then
        detect_i2c_address
    else
        log_message "info" "Skipping I2C detect, as user chose not to enable Buttons/LEDs."
    fi

    # 7) Setup main Quadify service
    setup_main_service
    # 8) Configure MPD
    configure_mpd
    # 9) Install CAVA from fork
    install_cava_from_fork
    # 10) Setup CAVA service
    setup_cava_service
    # 11) Configure Buttons & LEDs (comment/uncomment lines in main.py)
    configure_buttons_leds
    # 12) Setup Samba
    setup_samba
    # 13) Permissions
    set_permissions

    log_message "success" "Quadify installation complete! A reboot is required."

    # 14) Ask user if they'd like to reboot now
    while true; do
        read -rp "Reboot now? (y/n) " answer
        case $answer in
            [Yy]* )
                log_message "info" "Rebooting system now. See you on the other side!"
                reboot
                exit 0
                ;;
            [Nn]* )
                log_message "info" "Installation finished. Please reboot manually later."
                break
                ;;
            * )
                log_message "warning" "Please answer y or n."
                ;;
        esac
    done
}

main
