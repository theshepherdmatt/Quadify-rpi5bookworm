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
TOTAL_STEPS=20
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
#   New: Gather All User Preferences Up-Front
# ============================
get_user_preferences() {
    # 1) Ask about Buttons & LEDs
    BUTTONSLEDS_ENABLED=false
    while true; do
        read -rp "Enable Buttons & LEDs with MCP23017? (y/n): " answer
        case $answer in
            [Yy]* ) BUTTONSLEDS_ENABLED=true; break ;;
            [Nn]* ) BUTTONSLEDS_ENABLED=false; break ;;
            * ) log_message "warning" "Please answer y or n." ;;
        esac
    done

    # 2) Ask about IR remote support
    echo -e "\nWill you be using an IR remote? (y/n)"
    read -rp "Your choice: " ir_choice
    if [[ "$ir_choice" =~ ^[Yy] ]]; then
        IR_REMOTE_SUPPORT=true
        # Ask for GPIO selection immediately (this calls the existing function)
        enable_gpio_ir
        # Then gather the IR remote configuration selection
        gather_ir_remote_configuration
    else
        IR_REMOTE_SUPPORT=false
        log_message "info" "IR remote support skipped."
    fi
}

# ============================
#   New: Gather IR Remote Configuration Selection (Interactive)
# ============================
gather_ir_remote_configuration() {
    echo -e "\n${MAGENTA}Select your IR remote configuration:${NC}"
    echo "1) Default Quadify Remote"
    echo "2) Apple Remote A1156"
    echo "3) Apple Remote A1156 Alternative"
    echo "4) Apple Remote A1294"
    echo "5) Apple Remote A1294 Alternative"
    echo "6) Arcam ir-DAC-II Remote"
    echo "7) Atrix Remote"
    echo "8) Bluesound RC1"
    echo "9) Denon Remote RC-1204"
    echo "10) JustBoom IR Remote"
    echo "11) Marantz RC003PMCD"
    echo "12) Odroid Remote"
    echo "13) Philips CD723"
    echo "14) PDP Gaming Remote Control"
    echo "15) Samsung AA59-00431A"
    echo "16) Samsung_BN59-006XXA"
    echo "17) XBox 360 Remote"
    echo "18) XBox One Remote"
    echo "19) Xiaomi IR for TV box"
    echo "20) Yamaha RAV363"
    
    read -p "Enter your choice (1-20): " choice
    case "$choice" in
        1) remote_folder="Default Quadify Remote" ;;
        2) remote_folder="Apple Remote A1156" ;;
        3) remote_folder="Apple Remote A1156 Alternative" ;;
        4) remote_folder="Apple Remote A1294" ;;
        5) remote_folder="Apple Remote A1294 Alternative" ;;
        6) remote_folder="Arcam ir-DAC-II Remote" ;;
        7) remote_folder="Atrix Remote" ;;
        8) remote_folder="Bluesound RC1" ;;
        9) remote_folder="Denon Remote RC-1204" ;;
        10) remote_folder="JustBoom IR Remote" ;;
        11) remote_folder="Marantz RC003PMCD" ;;
        12) remote_folder="Odroid Remote" ;;
        13) remote_folder="Philips CD723" ;;
        14) remote_folder="PDP Gaming Remote Control" ;;
        15) remote_folder="Samsung AA59-00431A" ;;
        16) remote_folder="Samsung_BN59-006XXA" ;;
        17) remote_folder="XBox 360 Remote" ;;
        18) remote_folder="XBox One Remote" ;;
        19) remote_folder="Xiaomi IR for TV box" ;;
        20) remote_folder="Yamaha RAV363" ;;
        *) echo "Invalid selection. Exiting."; exit 1 ;;
    esac
    REMOTE_CONFIG_CHOICE=true
    log_message "info" "IR remote selected: $remote_folder"
}

# ============================
#   IR Remote Configuration Application (Later in the script)
# ============================
apply_ir_remote_configuration() {
    log_progress "Applying IR remote configuration for: $remote_folder"
    # If the default is selected, use the files directly from the lirc folder.
    if [ "$remote_folder" = "Default Quadify Remote" ]; then
        SOURCE_DIR="/home/volumio/Quadify/lirc/"
    else
        SOURCE_DIR="/home/volumio/Quadify/lirc/configurations/${remote_folder}/"
        if [ ! -d "$SOURCE_DIR" ]; then
            log_message "error" "Directory '$SOURCE_DIR' does not exist."
            exit 1
        fi
    fi
    DEST_DIR="/etc/lirc/"

    # Copy lircd.conf
    if [ -f "${SOURCE_DIR}lircd.conf" ]; then
        run_command "cp \"${SOURCE_DIR}lircd.conf\" \"${DEST_DIR}lircd.conf\""
        log_message "success" "Copied lircd.conf from $remote_folder."
    else
        log_message "error" "File '${SOURCE_DIR}lircd.conf' not found."
        exit 1
    fi

    # Copy lircrc
    if [ -f "${SOURCE_DIR}lircrc" ]; then
        run_command "cp \"${SOURCE_DIR}lircrc\" \"${DEST_DIR}lircrc\""
        log_message "success" "Copied lircrc from $remote_folder."
    else
        log_message "error" "File '${SOURCE_DIR}lircrc' not found."
        exit 1
    fi

    # Restart LIRC and IR listener services
    run_command "systemctl restart lircd"
    run_command "systemctl restart ir_listener.service"
    log_message "success" "IR services restarted."
    echo -e "\nIR remote configuration applied. Please reboot later for changes to take effect."
}

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
            lirc \
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
#   GPIO IR Overlay with User Selection
# ============================
enable_gpio_ir() {
    log_progress "Configuring GPIO IR overlay in userconfig.txt..."
    CONFIG_FILE="/boot/userconfig.txt"
    if [ ! -f "$CONFIG_FILE" ]; then
        run_command "touch \"$CONFIG_FILE\""
    fi

    # Prompt the user for the GPIO pin selection
    echo -e "\nSelect the GPIO pin for the IR receiver:"
    echo "1) GPIO 19"
    echo "2) GPIO 20"
    echo "3) GPIO 21"
    echo "4) GPIO 23"
    echo "5) GPIO 26 (Default)"
    echo "6) GPIO 27"
    read -p "Enter your choice (1-6) [Default 5]: " gpio_choice

    case "$gpio_choice" in
        1) selected_gpio=19 ;;
        2) selected_gpio=20 ;;
        3) selected_gpio=21 ;;
        4) selected_gpio=23 ;;
        5|"") selected_gpio=26 ;;  # default if 5 is chosen or nothing entered
        6) selected_gpio=27 ;;
        *) echo "Invalid selection. Using default GPIO 26." 
           selected_gpio=26 ;;
    esac

    if grep -q "^dtoverlay=gpio-ir" "$CONFIG_FILE"; then
        log_message "info" "GPIO IR overlay already present in $CONFIG_FILE. Updating to use GPIO $selected_gpio."
        run_command "sed -i 's/^dtoverlay=gpio-ir.*$/dtoverlay=gpio-ir,gpio_pin=${selected_gpio}/' \"$CONFIG_FILE\""
        log_message "success" "GPIO IR overlay updated to use GPIO $selected_gpio in $CONFIG_FILE."
    else
        echo "dtoverlay=gpio-ir,gpio_pin=${selected_gpio}" >> "$CONFIG_FILE"
        log_message "success" "GPIO IR overlay added to $CONFIG_FILE with GPIO $selected_gpio."
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
        update_config_i2c_address "$address"
    fi
    show_random_tip
}

update_config_i2c_address() {
    local detected_address="$1"
    CONFIG_FILE="/home/volumio/Quadify/config.yaml"
    if [[ -f "$CONFIG_FILE" ]]; then
        if grep -q "mcp23017_address:" "$CONFIG_FILE"; then
            run_command "sed -i \"s/mcp23017_address: 0x[0-9a-fA-F]\\{2\\}/mcp23017_address: 0x$detected_address/\" \"$CONFIG_FILE\""
            log_message "success" "Updated MCP23017 address in config.yaml to 0x$detected_address."
        else
            echo "mcp23017_address: 0x$detected_address" >> "$CONFIG_FILE"
            log_message "success" "Added MCP23017 address to config.yaml as 0x$detected_address."
        fi
    else
        log_message "error" "config.yaml not found at $CONFIG_FILE."
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
#   LED On Early Service
# ============================

setup_early_led8_service() {
    log_progress "Setting up early LED 8 indicator service..."
    SERVICE_SRC="/home/volumio/Quadify/service/early_led8.service"
    SERVICE_DST="/etc/systemd/system/early_led8.service"
    SCRIPT_SRC="/home/volumio/Quadify/scripts/early_led8.py"
    SCRIPT_DST="/home/volumio/Quadify/scripts/early_led8.py"

    if [[ -f "$SERVICE_SRC" && -f "$SCRIPT_SRC" ]]; then
        run_command "cp \"$SERVICE_SRC\" \"$SERVICE_DST\""
        run_command "chmod +x \"$SCRIPT_DST\""
        run_command "systemctl daemon-reload"
        run_command "systemctl enable early_led8.service"
        run_command "systemctl start early_led8.service"
        log_message "success" "early_led8.service installed and started."
    else
        log_message "error" "Missing $SERVICE_SRC or $SCRIPT_SRC."
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
        # Optionally start the service here:
        # run_command "systemctl start cava.service"
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
    MAIN_PY_PATH="/home/volumio/Quadify/src/main.py"
    if [[ ! -f "$MAIN_PY_PATH" ]]; then
        log_message "error" "Could not find main.py at $MAIN_PY_PATH."
        exit 1
    fi
    if [ "$BUTTONSLEDS_ENABLED" = false ]; then
        log_message "info" "Disabling 'buttons_leds' usage in main.py..."
        if grep -qE "^[^#]*\s*buttons_leds\s*=\s*ButtonsLEDController" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
        fi
        if grep -qE "^[^#]*\s*buttons_leds.start()" "$MAIN_PY_PATH"; then
            sed -i.bak '/buttons_leds.start()/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH"
        fi
        log_message "success" "Buttons/LEDs lines commented out."
    else
        log_message "info" "Enabling 'buttons_leds' usage in main.py..."
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
#   IR Controller
# ============================
install_lircrc() {
    log_progress "Installing LIRC configuration (lircrc) from repository..."
    LOCAL_LIRCRC="/home/volumio/Quadify/lirc/lircrc"
    DESTINATION="/etc/lirc/lircrc"
    if [ -f "$LOCAL_LIRCRC" ]; then
        run_command "cp \"$LOCAL_LIRCRC\" \"$DESTINATION\""
        log_message "success" "LIRC configuration (lircrc) copied to $DESTINATION."
    else
        log_message "error" "Local lircrc not found at $LOCAL_LIRCRC. Please ensure it is present."
        exit 1
    fi
}

install_lirc_configs() {
    log_progress "Installing LIRC configuration files..."
    LOCAL_LIRCRC="/home/volumio/Quadify/lirc/lircrc"
    LOCAL_LIRCD_CONF="/home/volumio/Quadify/lirc/lircd.conf"
    DEST_LIRCRC="/etc/lirc/lircrc"
    DEST_LIRCD_CONF="/etc/lirc/lircd.conf"
    if [ -f "$LOCAL_LIRCRC" ]; then
        run_command "cp \"$LOCAL_LIRCRC\" \"$DEST_LIRCRC\""
        log_message "success" "Copied lircrc to $DEST_LIRCRC."
    else
        log_message "error" "lircrc file not found at $LOCAL_LIRCRC."
        exit 1
    fi
    if [ -f "$LOCAL_LIRCD_CONF" ]; then
        run_command "cp \"$LOCAL_LIRCD_CONF\" \"$DEST_LIRCD_CONF\""
        log_message "success" "Copied lircd.conf to $DEST_LIRCD_CONF."
    else
        log_message "error" "lircd.conf file not found at $LOCAL_LIRCD_CONF."
        exit 1
    fi
    show_random_tip
}

setup_ir_listener_service() {
    log_progress "Setting up IR Listener service..."
    IR_SERVICE_FILE="/etc/systemd/system/ir_listener.service"
    LOCAL_IR_SERVICE="/home/volumio/Quadify/service/ir_listener.service"
    if [ -f "$LOCAL_IR_SERVICE" ]; then
        run_command "cp \"$LOCAL_IR_SERVICE\" \"$IR_SERVICE_FILE\""
        run_command "systemctl daemon-reload"
        run_command "systemctl enable ir_listener.service"
        run_command "systemctl start ir_listener.service"
        log_message "success" "ir_listener.service installed and started."
    else
        log_message "error" "ir_listener.service not found in /home/volumio/Quadify/service."
        exit 1
    fi
    show_random_tip
}

update_lirc_options() {
    log_progress "Updating LIRC options: setting driver to default..."
    sed -i 's|^driver\s*=.*|driver          = default|' /etc/lirc/lirc_options.conf
    log_message "success" "LIRC options updated: driver set to default."
    show_random_tip
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
#   Allow Volumio to Use systemctl Without Password
# ============================
ensure_sudoers_nopasswd() {
    log_progress "Ensuring sudoers entry for passwordless systemctl..."
    SUDOERS_LINE="volumio ALL=(ALL) NOPASSWD: /bin/systemctl"
    if ! grep -qF "$SUDOERS_LINE" /etc/sudoers; then
        echo "$SUDOERS_LINE" | EDITOR='tee -a' visudo > /dev/null
        log_message "success" "Added sudoers rule for systemctl without password."
    else
        log_message "info" "Sudoers rule for systemctl already present."
    fi
}


# ============================
#   Set Up run_update Wrapper
# ============================
setup_run_update_wrapper() {
    log_progress "Compiling and installing run_update setuid wrapper..."
    if [ -f "/home/volumio/Quadify/scripts/run_update.c" ]; then
        run_command "gcc -o /home/volumio/Quadify/scripts/run_update /home/volumio/Quadify/scripts/run_update.c"
        run_command "chown root:root /home/volumio/Quadify/scripts/run_update"
        run_command "chmod 4755 /home/volumio/Quadify/scripts/run_update"
        log_message "success" "run_update setuid wrapper compiled and installed."
    else
        log_message "warning" "run_update.c not found in /home/volumio/Quadify/scripts. Skipping setuid wrapper installation."
    fi
    show_random_tip
}

# ============================
#   Main Quadify Installation
# ============================
main() {
    check_root
    banner
	ensure_sudoers_nopasswd
    log_message "info" "Starting Quadify Installer..."
    
    # NEW: Gather all interactive answers at the very top
    get_user_preferences

    # 3) Install system dependencies
    install_system_dependencies

    # 4) Enable I2C/SPI
    enable_i2c_spi

    # 5) Upgrade pip
    upgrade_pip

    # 6) Install Python dependencies
    install_python_dependencies

    # 7) Detect I2C address if Buttons/LEDs enabled
    if [ "$BUTTONSLEDS_ENABLED" = true ]; then
        detect_i2c_address
        setup_early_led8_service
    else
        log_message "info" "Skipping I2C detect, as user chose not to enable Buttons/LEDs."
    fi

    # 8) Setup main Quadify service
    setup_main_service

    # 9) Configure MPD
    configure_mpd

    # 10) Install CAVA from fork
    install_cava_from_fork

    # 11) Setup CAVA service
    setup_cava_service

    # 12) Configure Buttons & LEDs (modify main.py)
    configure_buttons_leds

    # 13) Setup Samba
    setup_samba

    # 14) Install LIRC configuration (lircrc) from repository folder
    install_lircrc

    # 15) Install LIRC configuration files (lircrc and lircd.conf)
    install_lirc_configs

    # 16) Setup IR Listener service
    setup_ir_listener_service

    # 17) Update LIRC options to set driver to default
    update_lirc_options

    # NEW: If IR remote support was chosen, apply the configuration now.
    if [ "$IR_REMOTE_SUPPORT" = true ] && [ "$REMOTE_CONFIG_CHOICE" = true ]; then
        apply_ir_remote_configuration
    fi

    # 18) Set Permissions
    set_permissions

    # 19) Set up run_update setuid wrapper for automated updates
    setup_run_update_wrapper

    log_message "success" "Quadify installation complete! A reboot is required."

    # 20) Ask user if they'd like to reboot now
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
            * ) log_message "warning" "Please answer y or n." ;;
        esac
    done
}

main
