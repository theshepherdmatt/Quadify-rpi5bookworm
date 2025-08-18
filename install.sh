#!/bin/bash
set -e  # Exit on error
#set -x  # Debug

# ============================
#   Colour Code Definitions
# ============================
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; NC='\033[0m'

# ============================
#   Progress + Logging
# ============================
TOTAL_STEPS=22
CURRENT_STEP=0
LOG_FILE="install.log"
rm -f "$LOG_FILE"

banner() {
  echo -e "${MAGENTA}"
  echo "======================================================================================================"
  echo "   Quadify Installer: Volumio-based audio with custom UI, buttons, LEDs, safe power & clean shutdown"
  echo "======================================================================================================"
  echo -e "${NC}"
}

log_message() {
  local type="$1"; local message="$2"
  case "$type" in
    info)    echo -e "${BLUE}[INFO]${NC} $message" ;;
    success) echo -e "${GREEN}[SUCCESS]${NC} $message" ;;
    warning) echo -e "${YELLOW}[WARNING]${NC} $message" ;;
    error)   echo -e "${RED}[ERROR]${NC} $message" >&2 ;;
  esac
}

log_progress() {
  local message="$1"; CURRENT_STEP=$((CURRENT_STEP + 1))
  echo -e "${BLUE}[${CURRENT_STEP}/${TOTAL_STEPS}]${NC} $message"
}

run_command() {
  local cmd="$1"
  echo "Running: $cmd" >> "$LOG_FILE"
  echo -e "${MAGENTA}Running command...${NC}"
  bash -c "$cmd" >> "$LOG_FILE" 2>&1 || { log_message "error" "Command failed: $cmd. See $LOG_FILE"; exit 1; }
  echo -e "${GREEN}Done.${NC}"
}

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_message "error" "Please run as root or via sudo."
    exit 1
  fi
}

# ============================
#   Tips
# ============================
TIPS=(
  "Long-press any button to return home to the clock mode."
  "In Config, switch display modes — Modern, Original, or Minimal-Screen."
  "Try different screensavers under Config → Screensaver."
  "Tweak brightness in Config → Display for late-night listening."
  "Check new clock faces under the Clock menu!"
  "Need track info? Modern screen overlays sample rate & bit depth."
  "Help & logs: see install.log or 'journalctl -u quadify.service'."
  "Idle logic is improved — reduced risk of OLED burn-in."
)
show_random_tip(){ local i=$((RANDOM % ${#TIPS[@]})); log_message info "Tip: ${TIPS[$i]}"; }

# ============================
#   User Choices
# ============================
get_user_preferences() {
  # Buttons & LEDs (MCP23017)
  BUTTONSLEDS_ENABLED=false
  while true; do
    read -rp "Enable Buttons & LEDs with MCP23017? (y/n): " a
    case "$a" in [Yy]*) BUTTONSLEDS_ENABLED=true; break ;; [Nn]*) BUTTONSLEDS_ENABLED=false; break ;; *) log_message warning "Please answer y or n.";; esac
  done

  # On/Off SHIM question
  ONOFF_SHIM_ENABLED=false
  while true; do
    echo -e "\nDo you have a Pimoroni On/Off SHIM (or equivalent) connected?"
    read -rp "(y/n): " shim_choice
    case "$shim_choice" in
      [Yy]*) ONOFF_SHIM_ENABLED=true; log_message info "On/Off SHIM features will be installed and enabled."; break ;;
      [Nn]*) ONOFF_SHIM_ENABLED=false; log_message info "Skipping On/Off SHIM configuration."; break ;;
      *) log_message warning "Please answer y or n." ;;
    esac
  done

  # IR Remote
  echo -e "\nWill you be using an IR remote? (y/n)"
  read -rp "Your choice: " ir_choice
  if [[ "$ir_choice" =~ ^[Yy] ]]; then
    IR_REMOTE_SUPPORT=true
    enable_gpio_ir
    gather_ir_remote_configuration
  else
    IR_REMOTE_SUPPORT=false
    log_message info "IR remote support skipped."
  fi
}

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
  log_message info "IR remote selected: $remote_folder"
}

# ============================
#   System Dependencies
# ============================
install_system_dependencies() {
  log_progress "Installing system-level dependencies (brew a cuppa, this can take a bit)…"
  run_command "apt-get update"
  run_command "apt-get install -y \
    python3.7 python3.7-dev python3-pip \
    libjpeg-dev zlib1g-dev libfreetype6-dev \
    i2c-tools python3-smbus \
    libgirepository1.0-dev pkg-config libcairo2-dev \
    libffi-dev build-essential libxml2-dev libxslt1-dev libssl-dev \
    lirc lsof git curl rsync gcc make"
  log_message success "System-level dependencies installed."
  show_random_tip
}

upgrade_pip() {
  log_progress "Upgrading pip, setuptools, wheel…"
  local PYBIN=$(command -v python3.7 || command -v python3)
  run_command "$PYBIN -m pip install --upgrade pip setuptools wheel"
  log_message success "pip, setuptools, wheel upgraded."
  show_random_tip
}

install_python_dependencies() {
  log_progress "Installing Python dependencies (with CairoSVG pinned for Py3.7)…"
  local PYBIN=$(command -v python3.7 || command -v python3)

  # Core libs used by Quadify
  run_command "$PYBIN -m pip install --upgrade --ignore-installed smbus2 PyYAML"

  # pycairo first
  run_command "$PYBIN -m pip install --upgrade --ignore-installed pycairo"

  # CairoSVG stack (Py3.7-compatible pins)
  run_command "$PYBIN -m pip install --upgrade --ignore-installed \
    cairosvg==2.5.2 cairocffi==1.6.1 tinycss2==1.2.1 cssselect2==0.7.0 defusedxml==0.7.1"

  # Project requirements
  run_command "$PYBIN -m pip install --upgrade --ignore-installed -r /home/volumio/Quadify/requirements.txt"

  log_message success "Python dependencies installed."
  show_random_tip
}

# ============================
#   I2C & SPI
# ============================
enable_i2c_spi() {
  log_progress "Enabling I2C and SPI…"
  local CONFIG_FILE="/boot/userconfig.txt"
  [ -f "$CONFIG_FILE" ] || run_command "touch \"$CONFIG_FILE\""

  grep -q "^dtparam=spi=on" "$CONFIG_FILE" || echo "dtparam=spi=on" >> "$CONFIG_FILE"
  grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE" || echo "dtparam=i2c_arm=on" >> "$CONFIG_FILE"

  log_progress "Loading kernel modules…"
  run_command "modprobe i2c-dev"
  run_command "modprobe spi-bcm2835"

  if [ -e /dev/i2c-1 ]; then
    log_message success "/dev/i2c-1 present."
  else
    log_message warning "/dev/i2c-1 not found; trying i2c-bcm2708…"
    run_command "modprobe i2c-bcm2708"
    sleep 1
    [ -e /dev/i2c-1 ] || { log_message error "Could not initialise /dev/i2c-1. Check config/wiring."; exit 1; }
    log_message success "/dev/i2c-1 initialised."
  fi
  show_random_tip
}

# ============================
#   IR GPIO Overlay
# ============================
enable_gpio_ir() {
  log_progress "Configuring GPIO IR overlay…"
  local CONFIG_FILE="/boot/userconfig.txt"
  [ -f "$CONFIG_FILE" ] || run_command "touch \"$CONFIG_FILE\""

  echo -e "\nSelect the GPIO pin for the IR receiver:"
  echo "1) GPIO 19"
  echo "2) GPIO 20"
  echo "3) GPIO 21"
  echo "4) GPIO 23"
  echo "5) GPIO 26"
  echo "6) GPIO 27 (Default)"
  read -p "Enter your choice (1-6) [Default 6]: " gpio_choice
  case "$gpio_choice" in
    1) selected_gpio=19 ;; 2) selected_gpio=20 ;; 3) selected_gpio=21 ;;
    4) selected_gpio=23 ;; 6) selected_gpio=27 ;; *) selected_gpio=26 ;;
  esac

  if grep -q "^dtoverlay=gpio-ir" "$CONFIG_FILE"; then
    run_command "sed -i 's/^dtoverlay=gpio-ir.*$/dtoverlay=gpio-ir,gpio_pin=${selected_gpio}/' \"$CONFIG_FILE\""
    log_message success "Updated IR overlay to GPIO $selected_gpio."
  else
    echo "dtoverlay=gpio-ir,gpio_pin=${selected_gpio}" >> "$CONFIG_FILE"
    log_message success "Added IR overlay on GPIO $selected_gpio."
  fi
}

# ============================
#   Detect MCP23017 & write config.yaml
# ============================
detect_i2c_address() {
  log_progress "Detecting MCP23017 I²C address…"
  local I2CDET=$(command -v i2cdetect || echo /usr/sbin/i2cdetect)

  # Collect any hits in 0x20–0x27; prefer 0x20 (Pimoroni), else the first lowest found.
  local ADDR_HEX
  ADDR_HEX=$($I2CDET -y 1 | awk '
    {
      for (i=1;i<=NF;i++)
        if ($i ~ /^[0-9a-f][0-9a-f]$/ && strtonum("0x"$i) >= 0x20 && strtonum("0x"$i) <= 0x27)
          seen[$i]=1
    }
    END{
      if (seen["20"]) { print "20"; exit }
      for (n=0x20; n<=0x27; n++) {
        h = sprintf("%02x", n)
        if (seen[h]) { print h; exit }
      }
    }')

  if [ -z "$ADDR_HEX" ]; then
    log_message warning "No MCP23017 detected on i2c-1 (0x20–0x27)."
    return
  fi

  log_message success "MCP23017 found at I²C: 0x$ADDR_HEX"
  update_config_i2c_address "$ADDR_HEX"
}

update_config_i2c_address() {
  local HEX="$1"
  local CONFIG_FILE="/home/volumio/Quadify/config.yaml"
  log_progress "Writing MCP23017 address (0x$HEX) to $CONFIG_FILE…"

  MCP_ADDR="0x$HEX" python3 - <<'PY'
import os, pathlib, yaml
cfg = pathlib.Path("/home/volumio/Quadify/config.yaml")
data = {}
if cfg.exists():
    data = yaml.safe_load(cfg.read_text()) or {}

addr = int(os.environ["MCP_ADDR"], 16)   # store as integer (e.g., 32 for 0x20)
data["mcp23017_address"] = addr

# If your config also nests it, keep them in sync:
for key in ("buttons","hardware","peripherals","io"):
    if isinstance(data.get(key), dict):
        data[key]["mcp23017_address"] = addr

cfg.write_text(yaml.safe_dump(data, sort_keys=False))
print(f"Updated {cfg} to {hex(addr)}")
PY

  log_message success "config.yaml updated."
}

# ============================
#   On/Off SHIM overlays (kernel)
# ============================
configure_onoff_shim_overlays() {
  log_progress "Configuring kernel overlays for On/Off SHIM…"
  local CONFIG_FILE="/boot/userconfig.txt"
  [ -f "$CONFIG_FILE" ] || run_command "touch \"$CONFIG_FILE\""

  grep -q "^dtoverlay=gpio-shutdown" "$CONFIG_FILE" || \
    echo "dtoverlay=gpio-shutdown,gpio_pin=17,active_low=1,gpio_pull=up" >> "$CONFIG_FILE"

  grep -q "^dtoverlay=gpio-poweroff" "$CONFIG_FILE" || \
    echo "dtoverlay=gpio-poweroff,gpiopin=4,active_low=1" >> "$CONFIG_FILE"

  log_message success "Ensured gpio-shutdown (BCM17) & gpio-poweroff (BCM4)."
}

# ============================
#   Shutdown assets (scripts & services)
# ============================
install_shutdown_assets() {
  log_progress "Installing LED-off and clean poweroff assets…"

  # verify repo files exist
  for f in /home/volumio/Quadify/scripts/quadify-leds-off.py \
           /home/volumio/Quadify/scripts/clean-poweroff.sh \
           /home/volumio/Quadify/service/quadify-leds-off.service \
           /home/volumio/Quadify/service/volumio-clean-poweroff.service
  do
    [ -f "$f" ] || { log_message error "Missing $f"; exit 1; }
  done

  # install scripts
  run_command "install -m 755 /home/volumio/Quadify/scripts/quadify-leds-off.py /usr/local/bin/quadify-leds-off.py"
  run_command "install -m 755 /home/volumio/Quadify/scripts/clean-poweroff.sh /usr/local/bin/clean-poweroff.sh"

  # install services with correct perms
  run_command "install -m 644 /home/volumio/Quadify/service/quadify-leds-off.service /etc/systemd/system/quadify-leds-off.service"
  run_command "install -m 644 /home/volumio/Quadify/service/volumio-clean-poweroff.service /etc/systemd/system/volumio-clean-poweroff.service"

  run_command "systemctl daemon-reload"
  run_command "systemctl enable quadify-leds-off.service"
  run_command "systemctl enable volumio-clean-poweroff.service"

  log_message success "Shutdown services installed & enabled."
}

# ============================
#   Updater & Rollback assets
# ============================
install_updater_assets() {
  log_progress "Installing Quadify updater & rollback…"

  # Source paths inside the repo
  local UPDATER_SH="/home/volumio/Quadify/scripts/quadify_autoupdate.sh"
  local ROLLBACK_SH="/home/volumio/Quadify/scripts/quadify_rollback.sh"
  local UPDATE_SVC="/home/volumio/Quadify/service/quadify-update.service"
  local UPDATE_TMR="/home/volumio/Quadify/service/quadify-update.timer"   # optional

  # Sanity checks so we fail early if something’s missing
  for f in "$UPDATER_SH" "$ROLLBACK_SH" "$UPDATE_SVC"; do
    [ -f "$f" ] || { log_message error "Missing $f"; exit 1; }
  done

  # Ensure scripts are executable in-place (kept in repo path)
  run_command "chmod 755 \"$UPDATER_SH\" \"$ROLLBACK_SH\""

  # Install service (and optional timer) to systemd
  run_command "install -m 644 \"$UPDATE_SVC\" /etc/systemd/system/quadify-update.service"
  if [ -f "$UPDATE_TMR" ]; then
    run_command "install -m 644 \"$UPDATE_TMR\" /etc/systemd/system/quadify-update.timer"
  fi

  # Reload units and enable
  run_command "systemctl daemon-reload"
  run_command "systemctl enable quadify-update.service"
  if [ -f /etc/systemd/system/quadify-update.timer ]; then
    run_command "systemctl enable --now quadify-update.timer"
    log_message success "quadify-update.timer enabled."
  fi

  # Make sure log directory exists for the updater (harmless if already there)
  run_command "mkdir -p /var/log && touch /var/log/quadify_update.log || true"

  log_message success "Updater & rollback installed."
  show_random_tip
}

# ============================
#   Samba
# ============================
setup_samba() {
  log_progress "Configuring Samba for Quadify…"
  local SMB_CONF="/etc/samba/smb.conf"
  [ -f "$SMB_CONF.bak" ] || run_command "cp $SMB_CONF $SMB_CONF.bak"

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
  fi
  run_command "systemctl restart smbd"
  run_command "chown -R volumio:volumio /home/volumio/Quadify"
  run_command "chmod -R 777 /home/volumio/Quadify"

  if pdbedit -L | grep -q '^volumio:'; then
    log_message info "Samba user 'volumio' exists."
  else
    log_message info "Adding Samba user 'volumio' (you’ll be prompted for a password)."
    smbpasswd -a volumio
  fi
  log_message success "Samba ready."
  show_random_tip
}

# ============================
#   Services: main, early LED, CAVA, IR
# ============================
setup_main_service() {
  log_progress "Setting up main Quadify service…"
  local SERVICE_FILE="/etc/systemd/system/quadify.service"
  local LOCAL_SERVICE="/home/volumio/Quadify/service/quadify.service"
  [ -f "$LOCAL_SERVICE" ] || { log_message error "Missing $LOCAL_SERVICE"; exit 1; }
  run_command "install -m 644 \"$LOCAL_SERVICE\" \"$SERVICE_FILE\""
  run_command "systemctl daemon-reload"
  run_command "systemctl enable quadify.service"
  run_command "systemctl start quadify.service"
  log_message success "quadify.service installed and started."
  show_random_tip
}

setup_early_led8_service() {
  log_progress "Setting up early LED8 service…"
  local SERVICE_SRC="/home/volumio/Quadify/service/early_led8.service"
  local SERVICE_DST="/etc/systemd/system/early_led8.service"
  local SCRIPT_SRC="/home/volumio/Quadify/scripts/early_led8.py"
  [ -f "$SERVICE_SRC" ] && [ -f "$SCRIPT_SRC" ] || { log_message error "Missing $SERVICE_SRC or $SCRIPT_SRC"; exit 1; }
  run_command "install -m 644 \"$SERVICE_SRC\" \"$SERVICE_DST\""
  run_command "chmod +x \"$SCRIPT_SRC\""
  run_command "systemctl daemon-reload"
  run_command "systemctl enable early_led8.service"
  run_command "systemctl start early_led8.service"
  log_message success "early_led8.service installed and started."
}

configure_mpd() {
  log_progress "Configuring MPD FIFO…"
  local MPD_CONF_FILE="/volumio/app/plugins/music_service/mpd/mpd.conf.tmpl"
  local FIFO_OUTPUT="
audio_output {
    type            \"fifo\"
    name            \"my_fifo\"
    path            \"/tmp/cava.fifo\"
    format          \"44100:16:2\"
}"
  if grep -q "/tmp/cava.fifo" "$MPD_CONF_FILE"; then
    log_message info "FIFO output already present."
  else
    echo "$FIFO_OUTPUT" | tee -a "$MPD_CONF_FILE" >> "$LOG_FILE"
    log_message success "Added FIFO output to MPD conf."
  fi
  run_command "systemctl restart mpd"
  show_random_tip
}

check_cava_installed(){ command -v cava >/dev/null 2>&1; }

install_cava_from_fork() {
  log_progress "Installing CAVA (fork)…"
  local CAVA_REPO="https://github.com/theshepherdmatt/cava.git"
  local CAVA_INSTALL_DIR="/home/volumio/cava"
  if check_cava_installed; then log_message info "CAVA already installed. Skipping."; return; fi
  run_command "apt-get install -y libfftw3-dev libasound2-dev libncursesw5-dev libpulse-dev libtool automake autoconf gcc make pkg-config libiniparser-dev"
  if [[ ! -d "$CAVA_INSTALL_DIR" ]]; then run_command "git clone $CAVA_REPO $CAVA_INSTALL_DIR"; else run_command "cd $CAVA_INSTALL_DIR && git pull"; fi
  run_command "cd $CAVA_INSTALL_DIR && ./autogen.sh"
  run_command "cd $CAVA_INSTALL_DIR && ./configure"
  run_command "cd $CAVA_INSTALL_DIR && make"
  run_command "cd $CAVA_INSTALL_DIR && make install"
  log_message success "CAVA installed."
  show_random_tip
}

setup_cava_service() {
  log_progress "Installing CAVA service…"
  local LOCAL_CAVA_SERVICE="/home/volumio/Quadify/service/cava.service"
  local CAVA_SERVICE_FILE="/etc/systemd/system/cava.service"
  if [[ -f "$LOCAL_CAVA_SERVICE" ]]; then
    run_command "install -m 644 \"$LOCAL_CAVA_SERVICE\" \"$CAVA_SERVICE_FILE\""
    run_command "systemctl daemon-reload"
    run_command "systemctl enable cava.service"
    log_message success "cava.service installed."
  else
    log_message error "Missing $LOCAL_CAVA_SERVICE"
  fi
  show_random_tip
}

configure_buttons_leds() {
  local MAIN_PY_PATH="/home/volumio/Quadify/src/main.py"
  [ -f "$MAIN_PY_PATH" ] || { log_message error "Could not find $MAIN_PY_PATH"; exit 1; }
  if [ "$BUTTONSLEDS_ENABLED" = false ]; then
    log_message info "Disabling Buttons/LEDs in main.py…"
    sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH" || true
    sed -i.bak '/buttons_leds.start()/ s/^\(\s*\)/\1#/' "$MAIN_PY_PATH" || true
    log_message success "Buttons/LEDs lines commented out."
  else
    log_message info "Enabling Buttons/LEDs in main.py…"
    sed -i.bak '/buttons_leds\s*=\s*ButtonsLEDController/ s/^#//' "$MAIN_PY_PATH" || true
    sed -i.bak '/buttons_leds.start()/ s/^#//' "$MAIN_PY_PATH" || true
    log_message success "Buttons/LEDs lines uncommented."
  fi
}

install_lircrc() {
  log_progress "Installing base LIRC config…"
  local SRC="/home/volumio/Quadify/lirc/lircrc"
  local DST="/etc/lirc/lircrc"
  [ -f "$SRC" ] || { log_message error "Missing $SRC"; exit 1; }
  run_command "install -m 644 \"$SRC\" \"$DST\""
  log_message success "lircrc installed."
}

install_lirc_configs() {
  log_progress "Installing LIRC config files…"
  local SRC1="/home/volumio/Quadify/lirc/lircrc"
  local SRC2="/home/volumio/Quadify/lirc/lircd.conf"
  local DST1="/etc/lirc/lircrc"
  local DST2="/etc/lirc/lircd.conf"
  [ -f "$SRC1" ] || { log_message error "Missing $SRC1"; exit 1; }
  [ -f "$SRC2" ] || { log_message error "Missing $SRC2"; exit 1; }
  run_command "install -m 644 \"$SRC1\" \"$DST1\""
  run_command "install -m 644 \"$SRC2\" \"$DST2\""
  show_random_tip
}

setup_ir_listener_service() {
  log_progress "Installing IR Listener service…"
  local LOCAL_IR_SERVICE="/home/volumio/Quadify/service/ir_listener.service"
  local IR_SERVICE_FILE="/etc/systemd/system/ir_listener.service"
  [ -f "$LOCAL_IR_SERVICE" ] || { log_message error "Missing $LOCAL_IR_SERVICE"; exit 1; }
  run_command "install -m 644 \"$LOCAL_IR_SERVICE\" \"$IR_SERVICE_FILE\""
  run_command "systemctl daemon-reload"
  run_command "systemctl enable ir_listener.service"
  run_command "systemctl start ir_listener.service"
  log_message success "ir_listener.service installed and started."
  show_random_tip
}

update_lirc_options() {
  log_progress "Setting LIRC driver to default…"
  sed -i 's|^driver\s*=.*|driver          = default|' /etc/lirc/lirc_options.conf || true
  log_message success "LIRC options updated."
  show_random_tip
}

# ============================
#   Permissions / Sudoers
# ============================
set_permissions() {
  log_progress "Fixing ownership & permissions…"
  run_command "chown -R volumio:volumio /home/volumio/Quadify"
  run_command "chmod -R 755 /home/volumio/Quadify"
  log_message success "Permissions set."
}

ensure_sudoers_nopasswd() {
  log_progress "Ensuring sudoers entry for passwordless systemctl…"
  local SUDOERS_LINE="volumio ALL=(ALL) NOPASSWD: /bin/systemctl"
  grep -qF "$SUDOERS_LINE" /etc/sudoers || echo "$SUDOERS_LINE" | EDITOR='tee -a' visudo >/dev/null
  log_message success "Sudoers rule ensured."
}

# ============================
#   run_update Wrapper
# ============================
setup_run_update_wrapper() {
  log_progress "Installing run_update setuid wrapper (if present)…"
  local SRC="/home/volumio/Quadify/scripts/run_update.c"
  local BIN="/home/volumio/Quadify/scripts/run_update"
  if [ -f "$SRC" ]; then
    run_command "gcc -o \"$BIN\" \"$SRC\""
    run_command "chown root:root \"$BIN\""
    run_command "chmod 4755 \"$BIN\""
    log_message success "run_update installed."
  else
    log_message warning "run_update.c not found; skipping."
  fi
  show_random_tip
}

# ============================
#   MAIN
# ============================
main() {
  check_root
  banner
  ensure_sudoers_nopasswd
  log_message info "Starting Quadify Installer…"

  get_user_preferences
  install_system_dependencies
  enable_i2c_spi
  upgrade_pip
  install_python_dependencies

  if [ "$BUTTONSLEDS_ENABLED" = true ]; then
    detect_i2c_address
    setup_early_led8_service
  else
    log_message info "Skipping MCP23017 detection (Buttons/LEDs disabled)."
  fi

  setup_main_service

  # On/Off SHIM (only if user has one)
  if [ "$ONOFF_SHIM_ENABLED" = true ]; then
    configure_onoff_shim_overlays
    install_shutdown_assets
  else
    log_message info "On/Off SHIM overlays & shutdown services skipped by user choice."
  fi

  configure_mpd
  install_cava_from_fork
  setup_cava_service
  configure_buttons_leds
  setup_samba
  install_lircrc
  install_lirc_configs
  setup_ir_listener_service
  update_lirc_options
  set_permissions
  setup_run_update_wrapper
  install_updater_assets

  log_message success "Quadify installation complete! A reboot is required."

  while true; do
    read -rp "Reboot now? (y/n) " answer
    case $answer in
      [Yy]* ) log_message info "Rebooting…"; reboot; exit 0 ;;
      [Nn]* ) log_message info "Installation finished. Please reboot manually later."; break ;;
      * ) log_message warning "Please answer y or n." ;;
    esac
  done
}

main
