#!/usr/bin/env python3
# src/main.py

import RPi.GPIO as GPIO
GPIO.setwarnings(False)
import time
import threading
import logging
import yaml
import socket
import subprocess
import lirc
import os
import glob
import sys
from PIL import Image, ImageSequence

# UI / Hardware Imports
from display.screens.clock import Clock
from hardware.buttonsleds import ButtonsLEDController
from hardware.shutdown_system import shutdown_system
from display.screens.original_screen import OriginalScreen
from display.screens.modern_screen import ModernScreen
from display.screens.minimal_screen import MinimalScreen
from display.screens.system_info_screen import SystemInfoScreen
from display.screensavers.snake_screensaver import SnakeScreensaver
from display.screensavers.geo_screensaver import GeoScreensaver
from display.screensavers.bouncing_text_screensaver import BouncingTextScreensaver
from display.display_manager import DisplayManager
from managers.menu_manager import MenuManager
from managers.mode_manager import ModeManager
from managers.manager_factory import ManagerFactory
from controls.rotary_control import RotaryControl
from network.volumio_listener import VolumioListener

def load_config(config_path='/config.yaml'):
    abs_path = os.path.abspath(config_path)
    print(f"Attempting to load config from: {abs_path}")
    print(f"Does the file exist? {os.path.isfile(config_path)}")
    config = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            logging.debug(f"Configuration loaded from {config_path}.")
        except yaml.YAMLError as e:
            logging.error(f"Error loading config file {config_path}: {e}")
    else:
        logging.warning(f"Config file {config_path} not found. Using default configuration.")
    return config
    
FIRST_RUN_FLAG = '/data/quadify_first_run_done'

def has_seen_ready():
    """Returns True if user has already seen the ready_new screen."""
    return os.path.exists(FIRST_RUN_FLAG)

def set_has_seen_ready():
    """Creates the flag file to record that the ready_new screen was shown."""
    try:
        os.makedirs(os.path.dirname(FIRST_RUN_FLAG), exist_ok=True)
        with open(FIRST_RUN_FLAG, 'w') as f:
            f.write("shown")
    except Exception as e:
        print(f"Could not create first-run flag file: {e}")


def is_first_run():
    netconfigured = os.path.exists('/data/configuration/netconfigured')
    network_configs = glob.glob('/data/configuration/system_controller/network/*.json')
    return not (netconfigured and network_configs)

def is_network_online(host="8.8.8.8", port=53, timeout=3):
    """
    Returns True if the device can reach an external server (default: Google's DNS).
    This is a strong signal that the device is on Wi-Fi with internet access.
    """
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
        return True
    except Exception:
        return False

def show_gif_loop(gif_path, stop_condition, display_manager, logger):
    """Displays an animated GIF in a loop until stop_condition() returns True."""
    try:
        image = Image.open(gif_path)
        if not getattr(image, "is_animated", False):
            logger.warning(f"GIF '{gif_path}' is not animated.")
            return
    except Exception as e:
        logger.error(f"Failed to load GIF '{gif_path}': {e}")
        return
    logger.info(f"Displaying GIF: {gif_path}")
    required_size = display_manager.oled.size  # (width, height)

    while not stop_condition():
        for frame in ImageSequence.Iterator(image):
            if stop_condition():
                return
            # Always paste onto a blank image of the required size
            background = Image.new(display_manager.oled.mode, required_size)
            frame_converted = frame.convert(display_manager.oled.mode)
            # If frame size is smaller (common in GIFs), paste it at (0,0)
            background.paste(frame_converted, (0,0))
            display_manager.oled.display(background)
            frame_duration = frame.info.get('duration', 100) / 1000.0
            time.sleep(frame_duration)


def main():
    # --- Logging ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("QuadifyMain")

    # --- Config ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config.yaml')
    config = load_config(config_path)
    display_config = config.get('display', {})

    # --- DisplayManager ---
    display_manager = DisplayManager(display_config)

    # --- First Run: Show Network Setup GIFs ---
    if is_first_run():
        connecting_gif = display_config.get('connecting_path', 'connecting.gif')
        connected_gif = display_config.get('connected_path', 'connected.gif')

        logger.info("First run detected. Showing 'connecting' GIF until network is up.")

        # 1. Show "connecting" until network is truly online (ping check)
        show_gif_loop(
            connecting_gif,
            lambda: is_network_online(),
            display_manager,
            logger
        )

        logger.info("Network connected! Showing 'connected' GIF for 2 seconds.")
        # 2. Show "connected" GIF for 2 seconds
        show_gif_loop(
            connected_gif,
            lambda: True,  # play just once
            display_manager,
            logger
        )
        time.sleep(2)
        
    # --- Determine which ready GIF to show first ---
    if not has_seen_ready():
        first_ready_path = display_config.get('ready_new_path', 'ready_new.gif')
        logger.info("Showing 'ready_new.gif' for new user.")
        is_first_time_user = True
    else:
        first_ready_path = display_config.get('ready_gif_path', 'ready.gif')
        logger.info("Showing 'ready.gif' for returning user.")
        is_first_time_user = False

    import smbus2

    MCP23017_ADDRESS = 0x20   # Adjust to your address if needed
    MCP23017_GPIOA   = 0x12
    
    try:
        bus = smbus2.SMBus(1)
        # Turn LED8 off (clear bit 0)
        current = bus.read_byte_data(MCP23017_ADDRESS, MCP23017_GPIOA)
        bus.write_byte_data(MCP23017_ADDRESS, MCP23017_GPIOA, current & 0b11111110)
        bus.close()
    except Exception as e:
        print(f"Error turning off LED8: {e}")


    # --- Startup Logo ---
    logger.info("Displaying startup logo...")
    display_manager.show_logo(duration=6)
    logger.info("Startup logo display complete.")
    display_manager.clear_screen()
    logger.info("Screen cleared after logo display.")

    # --- Readiness GIF Threads/Events ---
    volumio_ready_event = threading.Event()
    min_loading_event = threading.Event()
    ready_stop_event = threading.Event()
    MIN_LOADING_DURATION = 6  # seconds

    # --- VolumioListener, Button, Rotary, etc ---
    volumio_cfg = config.get('volumio', {})
    volumio_host = volumio_cfg.get('host', 'localhost')
    volumio_port = volumio_cfg.get('port', 3000)
    volumio_listener = VolumioListener(host=volumio_host, port=volumio_port)

    # Loading GIF thread
    def show_loading():
        loading_gif_path = display_config.get('loading_gif_path', 'loading.gif')
        try:
            image = Image.open(loading_gif_path)
            if not getattr(image, "is_animated", False):
                logger.warning(f"Loading GIF '{loading_gif_path}' is not animated.")
                return
        except IOError:
            logger.error(f"Failed to load loading GIF '{loading_gif_path}'.")
            return
        logger.info("Displaying loading GIF during startup.")
        display_manager.clear_screen()
        time.sleep(0.1)
        while not (volumio_ready_event.is_set() and min_loading_event.is_set()):
            for frame in ImageSequence.Iterator(image):
                if volumio_ready_event.is_set() and min_loading_event.is_set():
                    logger.info("Volumio ready & min load done, stopping loading GIF.")
                    return
                display_manager.oled.display(frame.convert(display_manager.oled.mode))
                frame_duration = frame.info.get('duration', 100) / 1000.0
                time.sleep(frame_duration)
        logger.info("Exiting loading GIF display thread.")

    threading.Thread(target=show_loading, daemon=True).start()

    # Minimum loading duration
    def set_min_loading_event():
        time.sleep(MIN_LOADING_DURATION)
        min_loading_event.set()
        logger.info("Minimum loading duration has elapsed.")

    threading.Thread(target=set_min_loading_event, daemon=True).start()

    # On Volumio state change: set events, also handle ready_stop_event if playing
    def on_state_changed(sender, state):
        logger.info(f"Volumio state changed: {state}")
        if state.get('status') == 'play' and not ready_stop_event.is_set():
            logger.info("Detected playback start! Exiting ready screen.")
            ready_stop_event.set()
        if state.get('status') in ['play', 'stop', 'pause', 'unknown']:
            logger.info("Volumio is considered ready now.")
            volumio_ready_event.set()
            try:
                volumio_listener.state_changed.disconnect(on_state_changed)
            except Exception:
                pass

    volumio_listener.state_changed.connect(on_state_changed)


    # DummyModeManager and initial rotary input handler, for before full UI setup
    class DummyModeManager:
        def get_mode(self):
            return None

    mode_manager_placeholder = DummyModeManager()

    def on_button_press_inner():
        if not ready_stop_event.is_set():
            ready_stop_event.set()

    def on_long_press():
        pass

    def on_rotate(direction):
        pass

    rotary_control = RotaryControl(
        rotation_callback=on_rotate,
        button_callback=on_button_press_inner,
        long_press_callback=on_long_press,
        long_press_threshold=2.5
    )
    threading.Thread(target=rotary_control.start, daemon=True).start()

    # --- Wait for both loading events then run Ready GIF ---
    logger.info("Waiting for Volumio readiness & min load time.")
    volumio_ready_event.wait()
    min_loading_event.wait()
    logger.info("Volumio is ready & min loading time passed, proceeding to ready GIF.")

    show_gif_loop(first_ready_path, lambda: True, display_manager, logger)

    threading.Thread(
        target=display_manager.show_ready_gif_until_event,
        args=(ready_stop_event,),
        daemon=True
    ).start()
    ready_stop_event.wait()
    logger.info("Ready GIF exited, continuing to UI startup.")

    if is_first_time_user:
        set_has_seen_ready()


    # --- Now the main UI, ModeManager, screens, etc ---
    clock_config = config.get('clock', {})
    clock = Clock(display_manager, clock_config, volumio_listener)
    clock.logger = logging.getLogger("Clock")
    clock.logger.setLevel(logging.INFO)

    mode_manager = ModeManager(
        display_manager=display_manager,
        clock=clock,
        volumio_listener=volumio_listener,
        preference_file_path="../preference.json",
        config=config
    )

    manager_factory = ManagerFactory(
        display_manager=display_manager,
        volumio_listener=volumio_listener,
        mode_manager=mode_manager,
        config=config
    )
    manager_factory.setup_mode_manager()
    volumio_listener.mode_manager = mode_manager

    current_state = volumio_listener.get_current_state()
    if current_state and current_state.get("status") == "play":
        mode_manager.process_state_change(volumio_listener, current_state)
    else:
        mode_manager.trigger("to_menu")
    logger.info("Startup mode determined from current Volumio state.")

    buttons_leds = ButtonsLEDController(config_path=config_path)
    buttons_leds.start()

    # --- UI input handlers ---
    def on_rotate_ui(direction):
        current_mode = mode_manager.get_mode()
        if current_mode == 'original':
            volume_change = 40 if direction == 1 else -40
            mode_manager.original_screen.adjust_volume(volume_change)
        elif current_mode == 'modern':
            volume_change = 10 if direction == 1 else -20
            mode_manager.modern_screen.adjust_volume(volume_change)
            logger.debug(f"ModernScreen: Adjusted volume by {volume_change}")
        elif current_mode == 'minimal':
            volume_change = 10 if direction == 1 else -20
            mode_manager.minimal_screen.adjust_volume(volume_change)
            logger.debug(f"MinimalScreen: Adjusted volume by {volume_change}")
        elif current_mode == 'webradio':
            volume_change = 10 if direction == 1 else -20
            mode_manager.webradio_screen.adjust_volume(volume_change)
            logger.debug(f"WebRadioScreen: Adjusted volume by {volume_change}")
        elif current_mode == 'menu':
            mode_manager.menu_manager.scroll_selection(direction)
            logger.debug(f"Scrolled menu with direction: {direction}")
        elif current_mode == 'configmenu':
            mode_manager.config_menu.scroll_selection(direction)
        elif current_mode == 'systemupdate':
            mode_manager.system_update_menu.scroll_selection(direction)
        elif current_mode == 'screensaver':
            mode_manager.exit_screensaver()
        elif current_mode == 'clockmenu':
            mode_manager.clock_menu.scroll_selection(direction)
        elif current_mode == 'remotemenu':
            mode_manager.remote_menu.scroll_selection(direction)
        elif current_mode == 'screensavermenu':
            mode_manager.screensaver_menu.scroll_selection(direction)
        elif current_mode == 'displaymenu':
            mode_manager.display_menu.scroll_selection(direction)
        elif current_mode == 'tidal':
            mode_manager.tidal_manager.scroll_selection(direction)
        elif current_mode == 'qobuz':
            mode_manager.qobuz_manager.scroll_selection(direction)
        elif current_mode == 'spotify':
            mode_manager.spotify_manager.scroll_selection(direction)
        elif current_mode == 'playlists':
            mode_manager.playlist_manager.scroll_selection(direction)
        elif current_mode == 'radiomanager':
            mode_manager.radio_manager.scroll_selection(direction)
        elif current_mode == 'motherearthradio':
            mode_manager.motherearth_manager.scroll_selection(direction)
        elif current_mode == 'radioparadise':
            mode_manager.radioparadise_manager.scroll_selection(direction)
        elif current_mode == 'library':
            mode_manager.library_manager.scroll_selection(direction)
        elif current_mode == 'usblibrary':
            mode_manager.usb_library_manager.scroll_selection(direction)
        else:
            logger.warning(f"Unhandled mode: {current_mode}; no rotary action performed.")

    def on_button_press_ui():
        current_mode = mode_manager.get_mode()
        if current_mode == 'clock':
            # Use trigger to go to menu
            mode_manager.trigger("to_menu")
        elif current_mode == 'menu':
            mode_manager.menu_manager.select_item()
        elif current_mode == 'configmenu':
            mode_manager.config_menu.select_item()
        elif current_mode == 'remotemenu':
            mode_manager.remote_menu.select_item()
        elif current_mode == 'systemupdate':
            mode_manager.system_update_menu.select_item()
        elif current_mode == 'screensavermenu':
            mode_manager.screensaver_menu.select_item()
        elif current_mode == 'displaymenu':
            mode_manager.display_menu.select_item()
        elif current_mode == 'clockmenu':
            mode_manager.clock_menu.select_item()
        elif current_mode in ['original', 'modern', 'minimal']:
            logger.info(f"Button pressed in {current_mode} mode; toggling playback.")
            if current_mode == 'original':
                screen = mode_manager.original_screen
            elif current_mode == 'modern':
                screen = mode_manager.modern_screen
            elif current_mode == 'minimal':
                screen = mode_manager.minimal_screen
            else:
                screen = None
            if screen:
                screen.toggle_play_pause()
            else:
                logger.warning(f"No screen instance found for mode: {current_mode}")
        elif current_mode == 'playlists':
            mode_manager.playlist_manager.select_item()
        elif current_mode == 'tidal':
            mode_manager.tidal_manager.select_item()
        elif current_mode == 'qobuz':
            mode_manager.qobuz_manager.select_item()
        elif current_mode == 'spotify':
            mode_manager.spotify_manager.select_item()
        elif current_mode == 'library':
            mode_manager.library_manager.select_item()
        elif current_mode == 'radiomanager':
            mode_manager.radio_manager.select_item()
        elif current_mode == 'motherearthradio':
            mode_manager.motherearth_manager.select_item()
        elif current_mode == 'radioparadise':
            mode_manager.radioparadise_manager.select_item()
        elif current_mode == 'usblibrary':
            mode_manager.usb_library_manager.select_item()
        elif current_mode == 'screensaver':
            mode_manager.exit_screensaver()
        else:
            logger.warning(f"Unhandled mode: {current_mode}; no button action performed.")


    def on_long_press_ui():
        current_mode = mode_manager.get_mode()
        if current_mode == "menu":
            mode_manager.trigger("to_clock")
        else:
            mode_manager.trigger("back")

    # Attach UI handlers
    rotary_control.rotation_callback = on_rotate_ui
    rotary_control.button_callback = on_button_press_ui
    rotary_control.long_press_callback = on_long_press_ui

    # --- Command socket server for remote control ---
    def quadify_command_server(mode_manager, volumio_listener, display_manager, buttons_leds):
        sock_path = "/tmp/quadify.sock"
        try:
            os.remove(sock_path)
        except OSError:
            pass

        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.bind(sock_path)
        server_socket.listen(1)
        print(f"Quadify command server listening on {sock_path}")

        select_mapping = {
            "menu": lambda: mode_manager.menu_manager.select_item(),
            "tidal": lambda: mode_manager.tidal_manager.select_item(),
            "qobuz": lambda: mode_manager.qobuz_manager.select_item(),
            "spotify": lambda: mode_manager.spotify_manager.select_item(),
            "library": lambda: mode_manager.library_manager.select_item(),
            "radiomanager": lambda: mode_manager.radio_manager.select_item(),
            "motherearthradio": lambda: mode_manager.motherearth_manager.select_item(),
            "radioparadise": lambda: mode_manager.radioparadise_manager.select_item(),
            "playlists": lambda: mode_manager.playlist_manager.select_item(),
            "configmenu": lambda: mode_manager.config_menu.select_item(),
            "remotemenu": lambda: mode_manager.remote_menu.select_item(),
            "displaymenu": lambda: mode_manager.display_menu.select_item(),
            "clockmenu": lambda: mode_manager.clock_menu.select_item(),
            "systemupdate": lambda: mode_manager.system_update_menu.select_item(),
            "screensavermenu": lambda: mode_manager.screensaver_menu.select_item(),
            "systeminfo": lambda: mode_manager.system_info_screen.select_item(),
        }

        scroll_mapping = {
            "scroll_up": {
                "tidal": lambda: mode_manager.tidal_manager.scroll_selection(-1),
                "qobuz": lambda: mode_manager.qobuz_manager.scroll_selection(-1),
                "spotify": lambda: mode_manager.spotify_manager.scroll_selection(-1),
                "library": lambda: mode_manager.library_manager.scroll_selection(-1),
                "radiomanager": lambda: mode_manager.radio_manager.scroll_selection(-1),
                "motherearthradio": lambda: mode_manager.motherearth_manager.scroll_selection(-1),
                "radioparadise": lambda: mode_manager.radioparadise_manager.scroll_selection(-1),
                "playlists": lambda: mode_manager.playlist_manager.scroll_selection(-1),
                "configmenu": lambda: mode_manager.config_menu.scroll_selection(-1),
                "remotemenu": lambda: mode_manager.remote_menu.scroll_selection(-1),
                "displaymenu": lambda: mode_manager.display_menu.scroll_selection(-1),
                "clockmenu": lambda: mode_manager.clock_menu.scroll_selection(-1),
                "systemupdate": lambda: mode_manager.system_update_menu.scroll_selection(-1),
                "screensavermenu": lambda: mode_manager.screensaver_menu.scroll_selection(-1),
                "systeminfo": lambda: mode_manager.system_info_screen.scroll_selection(-1),
            },
            "scroll_down": {
                "tidal": lambda: mode_manager.tidal_manager.scroll_selection(1),
                "qobuz": lambda: mode_manager.qobuz_manager.scroll_selection(1),
                "spotify": lambda: mode_manager.spotify_manager.scroll_selection(1),
                "library": lambda: mode_manager.library_manager.scroll_selection(1),
                "radiomanager": lambda: mode_manager.radio_manager.scroll_selection(1),
                "motherearthradio": lambda: mode_manager.motherearth_manager.scroll_selection(1),
                "radioparadise": lambda: mode_manager.radioparadise_manager.scroll_selection(1),
                "playlists": lambda: mode_manager.playlist_manager.scroll_selection(1),
                "configmenu": lambda: mode_manager.config_menu.scroll_selection(1),
                "remotemenu": lambda: mode_manager.remote_menu.scroll_selection(1),
                "displaymenu": lambda: mode_manager.display_menu.scroll_selection(1),
                "clockmenu": lambda: mode_manager.clock_menu.scroll_selection(1),
                "systemupdate": lambda: mode_manager.system_update_menu.scroll_selection(1),
                "screensavermenu": lambda: mode_manager.screensaver_menu.scroll_selection(1),
                "systeminfo": lambda: mode_manager.system_info_screen.scroll_selection(1),
            }
        }

        while True:
            try:
                conn, _ = server_socket.accept()
                with conn:
                    data = conn.recv(1024)
                    if not data:
                        continue
                    command = data.decode("utf-8").strip()
                    print(f"Command received: {command}")
                    current_mode = mode_manager.get_mode()

                    if command == "home":
                        mode_manager.trigger("to_clock")
                    elif command == "shutdown":
                        shutdown_system(display_manager, buttons_leds, mode_manager)
                    elif command == "menu":
                        if current_mode == "clock":
                            mode_manager.trigger("to_menu")
                    elif command == "toggle":
                        mode_manager.toggle_play_pause()
                    elif command == "repeat":
                        print("Repeat command received. (Implement as needed)")
                    elif command == "select":
                        if current_mode in select_mapping:
                            select_mapping[current_mode]()
                        else:
                            print(f"No select mapping for mode: {current_mode}")
                    elif command in ["scroll_up", "scroll_down"]:
                        if current_mode in scroll_mapping[command]:
                            scroll_mapping[command][current_mode]()
                        else:
                            print(f"No scroll mapping for command: {command} in mode: {current_mode}")
                    elif command == "scroll_left":
                        if current_mode in ["menu", "configmenu"]:
                            active_menu = mode_manager.menu_manager if current_mode == "menu" else mode_manager.config_menu
                            active_menu.scroll_selection(-1)
                        else:
                            print(f"No mapping for scroll_left in mode: {current_mode}")
                    elif command == "scroll_right":
                        if current_mode in ["menu", "configmenu"]:
                            active_menu = mode_manager.menu_manager if current_mode == "menu" else mode_manager.config_menu
                            active_menu.scroll_selection(1)
                        else:
                            print(f"No mapping for scroll_right in mode: {current_mode}")
                    elif command == "seek_plus":
                        print("Seeking forward 10 seconds.")
                        subprocess.run(["volumio", "seek", "plus"], check=False)
                    elif command == "seek_minus":
                        print("Seeking backward 10 seconds.")
                        subprocess.run(["volumio", "seek", "minus"], check=False)
                    elif command == "skip_next":
                        print("Skipping to next track.")
                        subprocess.run(["volumio", "next"], check=False)
                    elif command == "skip_previous":
                        print("Skipping to previous track.")
                        subprocess.run(["volumio", "previous"], check=False)
                    elif command == "volume_plus":
                        volumio_listener.increase_volume()
                    elif command == "volume_minus":
                        volumio_listener.decrease_volume()
                    elif command == "back":
                        mode_manager.trigger("back")
                    else:
                        print(f"No mapping for command: {command}")
            except Exception as e:
                print(f"Error in command server: {e}")

    threading.Thread(
        target=quadify_command_server,
        args=(mode_manager, volumio_listener, display_manager, buttons_leds),
        daemon=True
    ).start()
    print("Quadify command server thread started.")

    # --- Main loop ---
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Quadify via KeyboardInterrupt.")
    finally:
        buttons_leds.stop()
        rotary_control.stop()
        try:
            volumio_listener.stop_listener()
        except Exception:
            pass
        clock.stop()
        display_manager.clear_screen()
        logger.info("Quadify shut down gracefully.")

if __name__ == "__main__":
    main()
