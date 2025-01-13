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

run_command() {
    local cmd="$1"
    eval "$cmd" >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        log_message "error" "Command failed: $cmd. Check $LOG_FILE for details."
        exit 1
    fi
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_message "error" "Please run as root or via sudo."
        exit 1
    fi
}

# ============================
#   System Dependencies
# ============================
install_system_dependencies() {
    log_progress "Installing system-level dependencies..."

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

    log_message "success" "System-level dependencies installed."
}

upgrade_pip() {
    log_progress "Upgrading pip, setuptools, and wheel..."
    run_command "python3.7 -m pip install --upgrade pip setuptools wheel"
    log_message "success" "pip, setuptools, and wheel upgraded."
}

install_python_dependencies() {
    log_progress "Installing Python dependencies..."

    # Force-install pycairo first
    run_command "python3.7 -m pip install --upgrade --ignore-installed pycairo"

    # Then the rest from requirements.txt
    run_command "python3.7 -m pip install --upgrade --ignore-installed -r /home/volumio/Quadify/requirements.txt"
    log_message "success" "Python dependencies installed."
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
        log_message "success" "quadify.service installed and started."
    else
        log_message "error" "quadify.service not found in /home/volumio/Quadify/service."
        exit 1
    fi
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
}

setup_cava_config() {
    log_progress "Setting up CAVA config..."

    CONFIG_DIR="/home/volumio/.config/cava"
    CONFIG_FILE="$CONFIG_DIR/config"
    REPO_CONFIG_FILE="/home/volumio/cava/config/default_config"

    run_command "mkdir -p \"$CONFIG_DIR\""

    if [[ ! -f "$CONFIG_FILE" ]]; then
        if [[ -f "$REPO_CONFIG_FILE" ]]; then
            run_command "cp \"$REPO_CONFIG_FILE\" \"$CONFIG_FILE\""
            log_message "info" "CAVA default config copied."
        else
            log_message "error" "No default_config in the cava repo."
            exit 1
        fi
    else
        log_message "info" "CAVA config already exists at $CONFIG_FILE."
    fi

    run_command "chown -R volumio:volumio \"$CONFIG_DIR\""
    log_message "success" "CAVA config setup complete."
}

setup_cava_service() {
    log_progress "Setting up CAVA service..."

    CAVA_SERVICE_FILE="/etc/systemd/system/cava.service"
    LOCAL_CAVA_SERVICE="/home/volumio/Quadify/service/cava.service"

    if [[ -f "$LOCAL_CAVA_SERVICE" ]]; then
        run_command "cp \"$LOCAL_CAVA_SERVICE\" \"$CAVA_SERVICE_FILE\""
        run_command "systemctl daemon-reload"
        #run_command "systemctl enable cava.service"
        #run_command "systemctl start cava.service"
        #log_message "success" "CAVA service started."
    else
        log_message "error" "cava.service not found in /home/volumio/Quadify/service."
    fi
}

setup_cava_vumeter_service() {
    log_progress "Setting up CAVA VU Meter service..."

    CAVA_VUMETER_SERVICE_FILE="/etc/systemd/system/cava_vumeter.service"
    LOCAL_VUMETER_SERVICE="/home/volumio/Quadify/service/cava_vumeter.service"

    if [[ -f "$LOCAL_VUMETER_SERVICE" ]]; then
        run_command "cp \"$LOCAL_VUMETER_SERVICE\" \"$CAVA_VUMETER_SERVICE_FILE\""
        run_command "systemctl daemon-reload"
        #run_command "systemctl enable cava_vumeter.service"
        # Don’t auto-start if you want to start only when user enters VU mode
        # But if you want it at boot, do:
        # run_command "systemctl start cava_vumeter.service"
        log_message "success" "CAVA VU meter service installed."
    else
        log_message "error" "cava_vumeter.service not found in /home/volumio/Quadify/service."
    fi
}


# ============================
#   Buttons + LEDs Handling
# ============================
configure_buttons_leds() {
    log_progress "Configuring Buttons and LEDs..."

    MAIN_PY_PATH="/home/volumio/Quadify/src/main.py"
    if [[ ! -f "$MAIN_PY_PATH" ]]; then
        log_message "error" "Could not find main.py at $MAIN_PY_PATH."
        exit 1
    fi

    while true; do
        read -rp "Enable Buttons & LEDs? (y/n): " yn
        case $yn in
            [Yy]* )
                log_message "info" "Enabling 'buttons_leds' usage in main.py..."
                # Uncomment the relevant lines
                if grep -qE "^[#]*\s*buttons_leds\s*=\s*ButtonsLEDController" "$MAIN_PY_PATH"; then
                    sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^#//' "$MAIN_PY_PATH"
                fi
                if grep -qE "^[#]*\s*buttons_leds.start()" "$MAIN_PY_PATH"; then
                    sed -i.bak '/buttons_leds.start()/ s/^#//' "$MAIN_PY_PATH"
                fi
                log_message "success" "Buttons/LEDs lines uncommented."
                break
                ;;
            [Nn]* )
                log_message "info" "Disabling 'buttons_leds' usage in main.py..."
                # Comment out if found
                if grep -qE "^[^#]*\s*buttons_leds\s*=\s*ButtonsLEDController" "$MAIN_PY_PATH"; then
                    sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
                fi
                if grep -qE "^[^#]*\s*buttons_leds.start()" "$MAIN_PY_PATH"; then
                    sed -i.bak '/buttons_leds.start()/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
                fi
                log_message "success" "Buttons/LEDs lines commented out."
                break
                ;;
            * )
                log_message "warning" "Please answer y or n."
                ;;
        esac
    done
    log_message "success" "Buttons/LEDs configuration complete."
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
    banner
    log_message "info" "Starting Quadify Installer..."
    check_root

    install_system_dependencies
    enable_i2c_spi
    upgrade_pip
    install_python_dependencies

    detect_i2c_address
    setup_main_service
    configure_mpd
    install_cava_from_fork
    setup_cava_config
    setup_cava_service
    configure_buttons_leds
    setup_samba
    set_permissions

    log_message "success" "Quadify installation complete! Review any warnings above if present."
}

main
