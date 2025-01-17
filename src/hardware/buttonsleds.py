import smbus2
import time
import threading
import logging
import subprocess
from enum import IntEnum
import yaml
from pathlib import Path

# MCP23017 Register Definitions
MCP23017_IODIRA = 0x00
MCP23017_IODIRB = 0x01
MCP23017_GPIOA  = 0x12
MCP23017_GPIOB  = 0x13
MCP23017_GPPUA  = 0x0C
MCP23017_GPPUB  = 0x0D

DEFAULT_MCP23017_ADDRESS = 0x20
SWAP_COLUMNS = True

class LED(IntEnum):
    LED1 = 0b10000000  # GPIOA7 => "Play" LED
    LED2 = 0b01000000  # GPIOA6 => "Pause/Stop" LED
    LED3 = 0b00100000  # GPIOA5 => e.g. Previous button LED
    LED4 = 0b00010000  # GPIOA4 => e.g. Next button LED
    LED5 = 0b00001000  # GPIOA3 => e.g. Repeat LED
    LED6 = 0b00000100  # GPIOA2 => e.g. Random LED
    LED7 = 0b00000010  # GPIOA1 => spare/custom
    LED8 = 0b00000001  # GPIOA0 => spare/custom

class ButtonsLEDController:
    """
    A hardware controller for an MCP23017 expander:
      - Writes to GPIOA (LEDs).
      - Reads a 4x2 button matrix from GPIOB (pins).
      - On each button press, calls 'volumio' CLI commands.
      - Continuously polls 'volumio status' to keep Play/Pause LED up to date.
    """

    def __init__(self, config_path='config.yaml', debounce_delay=0.1):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.ERROR)

        # Optional: console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(ch)

        self.logger.debug("Initializing ButtonsLEDController.")

        try:
            self.bus = smbus2.SMBus(1)
            self.logger.debug("I2C bus initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize I2C bus: {e}")
            self.bus = None

        self.debounce_delay = debounce_delay
        self.prev_button_state = [[1, 1], [1, 1], [1, 1], [1, 1]]
        self.button_map = [
            [1, 2],
            [3, 4],
            [5, 6],
            [7, 8],
        ]

        self.status_led_state = 0
        self.current_button_led_state = 0
        self.current_led_state = 0

        self.mcp23017_address = self._load_mcp_address(config_path)
        self._initialize_mcp23017()

        self.running = False
        self.thread = None
        self.monitor_thread = None

    def _load_mcp_address(self, config_path):
        self.logger.debug(f"Loading MCP23017 address from {config_path}")
        cfg_file = Path(config_path)
        if cfg_file.is_file():
            try:
                with open(cfg_file, 'r') as f:
                    config = yaml.safe_load(f)
                    address = config.get('mcp23017_address', DEFAULT_MCP23017_ADDRESS)
                    self.logger.debug(f"MCP23017 address loaded: 0x{address:02X}")
                    return address
            except yaml.YAMLError as e:
                self.logger.error(f"Error reading config file: {e}")
        else:
            self.logger.warning(f"Configuration file {config_path} not found. Using default MCP address.")
        self.logger.debug(f"Using default MCP23017 address: 0x{DEFAULT_MCP23017_ADDRESS:02X}")
        return DEFAULT_MCP23017_ADDRESS

    def _initialize_mcp23017(self):
        if not self.bus:
            self.logger.error("I2C bus not initialized; cannot init MCP23017.")
            return
        try:
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_IODIRA, 0x00)  # GPIOA => outputs
            self.logger.debug("GPIOA => outputs for LEDs.")

            # GPIOB => B0/B1 outputs (columns), B2-B7 inputs (rows)
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_IODIRB, 0xFC)
            self.logger.debug("GPIOB => B0/B1 outputs, B2-B7 inputs.")

            # Pull-ups on rows
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPPUB, 0xFC)
            self.logger.debug("Enabled pull-ups on B2-B7.")

            # Initially turn off all LEDs
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPIOA, 0x00)

            # B0/B1 high => columns inactive
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPIOB, 0x03)

            self.logger.info("MCP23017 init complete.")
        except Exception as e:
            self.logger.error(f"Error initializing MCP23017: {e}")
            self.bus = None

    def start(self):
        self.logger.debug("Starting ButtonsLEDController threads.")
        self.running = True

        # 1) Button scanning thread
        self.thread = threading.Thread(target=self._monitor_buttons_loop, name="ButtonMonitorThread")
        self.thread.start()

        # 2) Volumio status thread
        self.monitor_thread = threading.Thread(target=self._monitor_volumio_loop, name="VolumioMonitorThread")
        self.monitor_thread.start()

        self.logger.info("ButtonsLEDController started.")

    def stop(self):
        self.logger.debug("Stopping ButtonsLEDController threads.")
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join()
            self.logger.debug("ButtonMonitorThread joined.")

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join()
            self.logger.debug("VolumioMonitorThread joined.")

        self.logger.info("ButtonsLEDController stopped.")

    # ------------------------------
    #  Buttons
    # ------------------------------
    def _monitor_buttons_loop(self):
        self.logger.debug("Button monitoring loop started.")
        while self.running:
            if not self.bus:
                self.logger.error("I2C bus not available; stopping button loop.")
                break
            try:
                matrix = self._read_button_matrix()
                for row in range(4):
                    for col in range(2):
                        btn_id = self.button_map[row][col]
                        curr_state = matrix[row][col]
                        prev_state = self.prev_button_state[row][col]

                        # 1 => not pressed, 0 => pressed
                        if curr_state == 0 and prev_state == 1:
                            self.logger.info(f"Button {btn_id} pressed.")
                            self.handle_button_press(btn_id)

                        self.prev_button_state[row][col] = curr_state

                time.sleep(self.debounce_delay)
            except Exception as e:
                self.logger.error(f"Error in _monitor_buttons_loop: {e}")
                time.sleep(1)
        self.logger.debug("Button monitoring loop ended.")

    def _read_button_matrix(self):
        default_state = [[1, 1], [1, 1], [1, 1], [1, 1]]
        if not self.bus:
            return default_state

        matrix_state = [[1, 1], [1, 1], [1, 1], [1, 1]]
        try:
            for col in range(2):
                col_output = ~(1 << col) & 0x03  # col=0 => 0b10, col=1 => 0b01
                self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPIOB, col_output | 0xFC)
                time.sleep(0.005)
                row_in = self.bus.read_byte_data(self.mcp23017_address, MCP23017_GPIOB)
                for row in range(4):
                    bit_val = (row_in >> (row + 2)) & 0x01
                    if SWAP_COLUMNS:
                        matrix_state[row][1 - col] = bit_val
                    else:
                        matrix_state[row][col] = bit_val
        except Exception as e:
            self.logger.error(f"Error reading button matrix: {e}")
        return matrix_state

    def handle_button_press(self, button_id):
        """
        Now calls 'volumio' instead of 'mpc'.
        """
        self.current_button_led_state = 0

        try:
            if button_id == 1:
                # volumio toggle => toggles play/pause
                subprocess.run(["volumio", "toggle"], check=False)
                self.logger.debug("Executed 'volumio toggle'.")

            elif button_id == 2:
                # volumio stop => sets paused LED
                subprocess.run(["volumio", "stop"], check=False)
                self.logger.debug("Executed 'volumio stop'.")
                # Force the LED2 on
                self.status_led_state = LED.LED2.value
                self.control_leds()

            elif button_id == 3:
                # volumio next
                subprocess.run(["volumio", "next"], check=False)
                self.logger.debug("Executed 'volumio next'.")
                self.light_button_led_for(LED.LED4, 0.5)

            elif button_id == 4:
                # volumio previous
                subprocess.run(["volumio", "previous"], check=False)
                self.logger.debug("Executed 'volumio previous'.")
                self.light_button_led_for(LED.LED3, 0.5)

            elif button_id == 5:
                # volumio repeat => toggles repeat
                subprocess.run(["volumio", "repeat"], check=False)
                self.logger.debug("Executed 'volumio repeat'.")
                self.light_button_led_for(LED.LED5, 0.5)

            elif button_id == 6:
                # volumio random => toggles shuffle
                subprocess.run(["volumio", "random"], check=False)
                self.logger.debug("Executed 'volumio random'.")
                self.light_button_led_for(LED.LED6, 0.5)

            elif button_id == 7:
                self.logger.info("Button 7 pressed, no special action assigned.")
                self.light_button_led_for(LED.LED7, 0.5)

            elif button_id == 8:
                self.logger.info("Button 8 pressed => restarting 'quadify' service.")
                subprocess.run(["sudo", "systemctl", "restart", "quadify"], check=False)
                self.logger.debug("Executed 'systemctl restart quadify'.")
                self.light_button_led_for(LED.LED8, 0.5)

            else:
                self.logger.warning(f"Unhandled button ID: {button_id}")

        except Exception as e:
            self.logger.error(f"Error handling button {button_id}: {e}")

    # ------------------------------
    #  Volumio Monitor
    # ------------------------------
    def _monitor_volumio_loop(self):
        """
        Checks 'volumio status' every 2 seconds to keep LED1 or LED2 lit
        depending on playback state (play vs pause/stop).
        """
        self.logger.debug("Volumio monitor loop started.")
        while self.running:
            try:
                self.update_play_pause_led()
            except Exception as e:
                self.logger.error(f"Exception in Volumio monitor loop: {e}")
            time.sleep(2)
        self.logger.debug("Volumio monitor loop ended.")

    def update_play_pause_led(self):
        """
        Uses 'volumio status' => parse 'status': 'play' or 'pause' or 'stop'.
        Then sets LED1 if playing, else LED2.
        """
        try:
            # Run volumio status command
            res = subprocess.run(["volumio", "status"], capture_output=True, text=True)
            if res.returncode == 0:
                out = res.stdout.lower()

                # Looking for something like:  "status: play"
                # or "status: pause", etc.  You might have to adapt if volumio CLI differs.
                if "status: play" in out:
                    self.logger.debug("Volumio => playing => LED1 on.")
                    self.status_led_state = LED.LED1.value
                elif "status: pause" in out or "status: stop" in out:
                    self.logger.debug("Volumio => paused/stopped => LED2 on.")
                    self.status_led_state = LED.LED2.value
                else:
                    self.logger.debug("Volumio => unknown => no LED lit.")
                    self.status_led_state = 0

                self.control_leds()
            else:
                self.logger.warning("volumio status command failed; no LED update.")
        except Exception as e:
            self.logger.error(f"update_play_pause_led: {e}")

    # ------------------------------
    #  LED Helpers
    # ------------------------------
    def light_button_led_for(self, led, duration):
        self.current_button_led_state = led.value
        self.control_leds()
        threading.Timer(duration, self.reset_button_led).start()

    def reset_button_led(self):
        self.current_button_led_state = 0
        self.control_leds()

    def control_leds(self):
        """Combine status_led_state & ephemeral, write to MCP23017 GPIOA."""
        total_state = self.status_led_state | self.current_button_led_state
        self.logger.debug(
            f"LED states => status: {bin(self.status_led_state)}, "
            f"button: {bin(self.current_button_led_state)}, total: {bin(total_state)}"
        )
        if total_state != self.current_led_state:
            if self.bus:
                try:
                    self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPIOA, total_state)
                    self.current_led_state = total_state
                    self.logger.info(f"LED state updated: {bin(total_state)}")
                except Exception as e:
                    self.logger.error(f"Error setting LED state: {e}")
            else:
                self.logger.error("No I2C bus for LED control.")
        else:
            self.logger.debug("LED state unchanged; no update needed.")

    def clear_all_leds(self):
        """Turn off all LEDs."""
        if not self.bus:
            self.logger.warning("No I2C bus to clear LEDs.")
            return
        try:
            self.bus.write_byte_data(self.mcp23017_address, MCP23017_GPIOA, 0x00)
            self.current_led_state = 0
            self.logger.debug("All LEDs cleared.")
        except Exception as e:
            self.logger.error(f"Error clearing all LEDs: {e}")

    def close(self):
        """Close the I2C bus if needed."""
        if self.bus:
            self.bus.close()
            self.logger.info("Closed SMBus.")
