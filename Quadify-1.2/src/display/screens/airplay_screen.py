import os
import logging
from PIL import Image, ImageDraw, ImageFont
import threading
import time
import requests
from io import BytesIO

class AirPlayScreen:
    """
    A basic AirPlay screen that displays:
      - Title (truncated if needed)
      - Artist
      - A horizontal separator line
      - Service info (e.g. “AirPlay”) and quality info (e.g. bitdepth/samplerate)
    Instead of trying to download album art (which for AirPlay is not valid), it uses
    a static AirPlay icon (preloaded in DisplayManager).
    """
    def __init__(self, display_manager, volumio_listener, mode_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        self.display_manager = display_manager
        self.volumio_listener = volumio_listener
        self.mode_manager = mode_manager

        # State and thread control
        self.is_active = False
        self.latest_state = None
        self.current_state = None
        self.state_lock = threading.Lock()
        self.update_event = threading.Event()
        self.stop_event = threading.Event()

        # Fonts (use the same keys as in WebRadioScreen or adjust as desired)
        self.font_title = display_manager.fonts.get('radio_title', ImageFont.load_default())
        self.font_small = display_manager.fonts.get('radio_small', ImageFont.load_default())
        self.font_label = display_manager.fonts.get('radio_bitrate', ImageFont.load_default())

        # Background update thread
        self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("AirPlayScreen: Started background update thread.")

        # Connect to Volumio state changes
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)
        self.logger.info("AirPlayScreen initialised.")

        # For repeated-update suppression, track the last state (and timestamp)
        self.last_state = None

    def on_volumio_state_change(self, sender, state):
        """
        Update display only if active and if the service indicates AirPlay.
        Also, if the state data has not changed (for example if title/artist are unchanged)
        within a threshold, ignore the update.
        """
        if not self.is_active:
            self.logger.debug("AirPlayScreen: ignoring state change; screen not active.")
            return

        if state.get("service", "").lower() not in ["airplay_emulation"]:
            self.logger.debug("AirPlayScreen: ignoring state change; service is not AirPlay.")
            return

        current_time = time.time()
        THRESHOLD = 3.0  # seconds; adjust as needed

        with self.state_lock:
            # Compare with last state if available.
            if self.last_state:
                same_track = (
                    state.get("title") == self.last_state.get("title") and
                    state.get("artist") == self.last_state.get("artist")
                )
                last_time = self.last_state.get("timestamp", 0)
                if same_track and (current_time - last_time < THRESHOLD):
                    self.logger.debug("AirPlayScreen: Ignoring repeated play event (same track within threshold).")
                    return
            # Stamp the state with current timestamp and save
            state["timestamp"] = current_time
            self.last_state = state.copy()
            self.latest_state = state.copy()
        self.update_event.set()

    def update_display_loop(self):
        """Wait for state updates (or timeout) and then redraw the screen."""
        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            with self.state_lock:
                if triggered and self.latest_state:
                    self.current_state = self.latest_state.copy()
                    self.latest_state = None
                    self.update_event.clear()
            if self.is_active and self.mode_manager.get_mode() == "airplay" and self.current_state:
                self.draw_display(self.current_state)

    def start_mode(self):
        if self.mode_manager.get_mode() != "airplay":
            self.logger.warning("AirPlayScreen: Mode is not 'airplay'; forcing start anyway.")
            # Optionally, you can force the state here:
            # self.mode_manager.machine.set_state("airplay")
        self.is_active = True
        try:
            if self.volumio_listener and self.volumio_listener.socketIO:
                self.logger.debug("AirPlayScreen: Forcing getState from Volumio.")
                self.volumio_listener.socketIO.emit("getState", {})
        except Exception as e:
            self.logger.warning(f"AirPlayScreen: Failed to emit 'getState'. Error => {e}")
        if not self.update_thread.is_alive():
            self.stop_event.clear()
            self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
            self.update_thread.start()
            self.logger.debug("AirPlayScreen: Display update thread restarted.")

    def stop_mode(self):
        """
        Called when leaving 'airplay' mode.
        """
        if not self.is_active:
            self.logger.debug("AirPlayScreen: stop_mode called but not active.")
            return

        self.is_active = False
        self.stop_event.set()
        self.update_event.set()

        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
            self.logger.debug("AirPlayScreen: Display update thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("AirPlayScreen: Stopped mode and cleared screen.")

    def get_albumart(self, url):
        """
        For AirPlay we do not download album art from a URL (which may be invalid).
        Instead, we return None so that our draw_display() method can default to using
        a static AirPlay icon.
        """
        return None

    def draw_display(self, data):
        """
        Draw the AirPlay screen with:
         - Title (truncated to 20 characters)
         - Artist
         - A horizontal separator line
         - Service info (or stream) and quality info (bitdepth/samplerate)
         - Instead of album art, use the preloaded 'airplay' icon.
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)
        margin = 5

        screen_width, screen_height = self.display_manager.oled.size

        # Extract data values with fallbacks.
        title = data.get("title", "AirPlay")
        if len(title) > 20:
            title = title[:20] + "…"
        artist = data.get("artist", "Unknown Artist")
        service = data.get("service", "AirPlay").strip()
        quality = f"{data.get('bitdepth', 'N/A')} / {data.get('samplerate', 'N/A')}"

        # Set vertical positions (adjust as needed).
        title_y = margin
        artist_y = margin + 15
        divider_y = margin + 30
        service_y = divider_y + 5
        quality_y = divider_y + 15

        # Draw title and artist.
        draw.text((margin, title_y), title, font=self.font_title, fill="white")
        draw.text((margin, artist_y), artist, font=self.font_small, fill="white")

        # Draw horizontal separator line. Leave space on the right for the icon.
        icon_width = 60
        gap = 15
        line_end_x = screen_width - margin - icon_width - gap
        draw.line((margin, divider_y, line_end_x, divider_y), fill="white")

        # Draw service and quality info.
        draw.text((margin, service_y), service, font=self.font_small, fill="white")
        draw.text((margin, quality_y), quality, font=self.font_label, fill="white")

        # Instead of downloading album art, use a static AirPlay icon.
        airplay_icon = self.display_manager.icons.get("airplay")
        if airplay_icon:
            icon_size = (60, 60)
            airplay_icon = airplay_icon.resize(icon_size, Image.LANCZOS)
            art_x = screen_width - icon_size[0] - margin
            art_y = margin
            base_image.paste(airplay_icon, (art_x, art_y))

        # Finally, update the OLED.
        self.display_manager.oled.display(base_image)
        self.logger.debug("AirPlayScreen: Display updated.")

    def adjust_volume(self, volume_change):
        """
        Adjust volume via an external call.
        Emits a volume change command to Volumio.
        """
        if not self.volumio_listener:
            self.logger.error("AirPlayScreen: No volumio_listener; cannot adjust volume.")
            return

        if self.latest_state is None:
            self.logger.debug("AirPlayScreen: latest_state is None; assuming volume=100.")
            self.latest_state = {"volume": 100}

        with self.state_lock:
            curr_vol = self.latest_state.get("volume", 100)
            new_vol = max(0, min(int(curr_vol) + volume_change, 100))

        self.logger.info(f"AirPlayScreen: Adjusting volume from {curr_vol} to {new_vol}.")
        try:
            if volume_change > 0:
                self.volumio_listener.socketIO.emit("volume", "+")
            elif volume_change < 0:
                self.volumio_listener.socketIO.emit("volume", "-")
            else:
                self.volumio_listener.socketIO.emit("volume", new_vol)
        except Exception as e:
            self.logger.error(f"AirPlayScreen: Error adjusting volume => {e}")

    def toggle_play_pause(self):
        """Toggle play/pause if connected."""
        self.logger.info("AirPlayScreen: Toggling play/pause.")
        if not self.volumio_listener or not self.volumio_listener.is_connected():
            self.logger.warning("AirPlayScreen: Not connected to Volumio; cannot toggle.")
            return
        try:
            self.volumio_listener.socketIO.emit("toggle", {})
            self.logger.debug("AirPlayScreen: Emitted 'toggle' event.")
        except Exception as e:
            self.logger.error(f"AirPlayScreen: Toggle play/pause failed => {e}")

    def display_airplay_info(self):
        """Manually refresh the display with the current state."""
        if not self.is_active:
            self.logger.info("AirPlayScreen: display_airplay_info called, but mode is not active.")
            return

        state = self.volumio_listener.get_current_state()
        if state:
            self.draw_display(state)
        else:
            self.logger.warning("AirPlayScreen: No current Volumio state available to display.")
