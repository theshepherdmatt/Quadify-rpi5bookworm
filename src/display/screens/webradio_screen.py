import os
import logging
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont
import threading
import math
import time

FIFO_PATH = "/tmp/display.fifo"  # Path to the FIFO for CAVA data

class WebRadioScreen:
    """
    A simplified, 'modern-style' WebRadio screen featuring:
      - A single line (station/song) centered at the top
      - A 'WebRadio' label underneath
      - Volume and bitrate info drawn under the title (like the minimal screen)
      - Station album art on the right (in place of a duration circle)
      - An unusual spectrum drawn as a waveform at the bottom (Option 2)
    """

    def __init__(self, display_manager, volumio_listener, mode_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        self.display_manager = display_manager
        self.volumio_listener = volumio_listener
        self.mode_manager = mode_manager

        # State & screen activity
        self.is_active = False
        self.latest_state = None
        self.current_state = None
        self.state_lock = threading.Lock()
        self.update_event = threading.Event()
        self.stop_event = threading.Event()

        # Spectrum / CAVA
        self.running_spectrum = False
        self.spectrum_thread = None
        self.spectrum_bars = []

        # Fonts (ensure these exist in display_manager.fonts or define fallback)
        self.font_station = display_manager.fonts.get('radio_title', ImageFont.load_default())
        self.font_label = display_manager.fonts.get('radio_bitrate', ImageFont.load_default())

        # Scrolling (optional)
        self.scroll_offset_station = 0
        self.scroll_speed = 2

        # Display update thread
        self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("WebRadioScreen: Started background update thread.")

        # Connect to Volumio listener
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)
        self.logger.info("WebRadioScreen initialized.")

    # ------------------------------------------------------------------
    # Volumio State Change
    # ------------------------------------------------------------------
    def on_volumio_state_change(self, sender, state):
        """
        Triggered whenever VolumioListener emits a state_changed signal.
        Only update if:
          - self.is_active is True
          - mode_manager.get_mode() == 'webradio'
          - service == 'webradio'
        """
        if not self.is_active:
            self.logger.debug("WebRadioScreen: ignoring state change; screen not active.")
            return

        if self.mode_manager.get_mode() != 'webradio':
            self.logger.debug("WebRadioScreen: ignoring state change; not in webradio mode.")
            return

        if state.get("service") not in ["webradio", "motherearthradio", "radio_paradise"]:
            self.logger.debug("WebRadioScreen: ignoring state change; service not in allowed list.")
            return

        self.logger.debug(f"WebRadioScreen: state changed => {state}")
        with self.state_lock:
            self.latest_state = state
        self.update_event.set()

    # ------------------------------------------------------------------
    # Background Update Loop
    # ------------------------------------------------------------------
    def update_display_loop(self):
        """
        Runs in the background to handle display updates.
        Waits on update_event or times out periodically so we can animate text or update the spectrum.
        """
        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            with self.state_lock:
                if triggered and self.latest_state:
                    # New state received from Volumio
                    self.current_state = self.latest_state.copy()
                    self.latest_state = None
                    self.update_event.clear()
            if self.is_active and self.mode_manager.get_mode() == 'webradio' and self.current_state:
                self.draw_display(self.current_state)

    # ------------------------------------------------------------------
    # Start/Stop
    # ------------------------------------------------------------------
    def start_mode(self):
        """
        Called when ModeManager transitions to 'webradio' mode.
        """
        if self.mode_manager.get_mode() != 'webradio':
            self.logger.warning("WebRadioScreen: Attempted start, but mode != 'webradio'.")
            return

        self.is_active = True
        self.reset_scrolling()

        # Force immediate getState from Volumio
        try:
            if self.volumio_listener and self.volumio_listener.socketIO:
                self.logger.debug("WebRadioScreen: Forcing getState from Volumio.")
                self.volumio_listener.socketIO.emit("getState", {})
        except Exception as e:
            self.logger.warning(f"WebRadioScreen: Failed to emit 'getState'. Error => {e}")

        # Start reading the FIFO if cava_enabled is True
        if self.mode_manager.config.get("cava_enabled", False):
            if not self.spectrum_thread or not self.spectrum_thread.is_alive():
                self.running_spectrum = True
                self.spectrum_thread = threading.Thread(target=self._read_fifo, daemon=True)
                self.spectrum_thread.start()
                self.logger.info("WebRadioScreen: Spectrum reading thread started.")
        else:
            self.logger.info("WebRadioScreen: Spectrum is disabled globally, skipping FIFO reading.")

        # Restart update_thread if needed
        if not self.update_thread.is_alive():
            self.stop_event.clear()
            self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
            self.update_thread.start()
            self.logger.debug("WebRadioScreen: display update thread restarted.")

    def stop_mode(self):
        """
        Called when leaving 'webradio' mode in ModeManager.
        """
        if not self.is_active:
            self.logger.debug("WebRadioScreen: stop_mode called but not active.")
            return

        self.is_active = False
        self.stop_event.set()
        self.update_event.set()

        # Stop spectrum thread if running
        self.running_spectrum = False
        if self.spectrum_thread and self.spectrum_thread.is_alive():
            self.spectrum_thread.join(timeout=1)
            self.logger.info("WebRadioScreen: Spectrum thread stopped.")

        # Stop update thread if running
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
            self.logger.debug("WebRadioScreen: display update thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("WebRadioScreen: Stopped mode and cleared screen.")

    # ------------------------------------------------------------------
    # Spectrum FIFO
    # ------------------------------------------------------------------
    def _read_fifo(self):
        """
        Continuously read from the CAVA FIFO and store bars in self.spectrum_bars.
        """
        if not os.path.exists(FIFO_PATH):
            self.logger.error(f"WebRadioScreen: FIFO {FIFO_PATH} not found.")
            return

        self.logger.debug("WebRadioScreen: reading from FIFO for spectrum data.")
        try:
            with open(FIFO_PATH, "r") as fifo:
                while self.running_spectrum:
                    line = fifo.readline().strip()
                    if line:
                        bars = [int(x) for x in line.split(";") if x.isdigit()]
                        self.spectrum_bars = bars
        except Exception as e:
            self.logger.error(f"WebRadioScreen: error reading FIFO => {e}")

    # ------------------------------------------------------------------
    # Scrolling
    # ------------------------------------------------------------------
    def reset_scrolling(self):
        self.logger.debug("WebRadioScreen: resetting scroll offsets.")
        self.scroll_offset_station = 0

    def update_scroll(self, text, font, max_width, scroll_offset):
        """
        Basic continuous scrolling logic for text that might not fit on screen.
        """
        text_width, _ = font.getsize(text)
        if text_width <= max_width:
            return text, 0, False  # no scroll needed

        scroll_offset += self.scroll_speed
        if scroll_offset > text_width:
            scroll_offset = 0

        return text, scroll_offset, True

    # ------------------------------------------------------------------
    # Volume Adjustment
    # ------------------------------------------------------------------
    def adjust_volume(self, volume_change):
        """
        Adjust volume from an external call (e.g. a rotary encoder).
        This emits a volume change to Volumio via the socketIO connection.
        """
        if not self.volumio_listener:
            self.logger.error("WebRadioScreen: no volumio_listener, cannot adjust volume.")
            return

        if self.latest_state is None:
            self.logger.debug("WebRadioScreen: latest_state is None, assuming volume=100.")
            self.latest_state = {"volume": 100}

        with self.state_lock:
            curr_vol = self.latest_state.get("volume", 100)
            new_vol = max(0, min(int(curr_vol) + volume_change, 100))
        
        self.logger.info(f"WebRadioScreen: Adjusting volume from {curr_vol} to {new_vol}.")
        try:
            if volume_change > 0:
                self.volumio_listener.socketIO.emit("volume", "+")
            elif volume_change < 0:
                self.volumio_listener.socketIO.emit("volume", "-")
            else:
                self.volumio_listener.socketIO.emit("volume", new_vol)
        except Exception as e:
            self.logger.error(f"WebRadioScreen: error adjusting volume => {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def get_display_text(self, state):
        """
        Decide what text to display based on Volumio's 'title' and 'artist'.
        """
        title = state.get("title", "") or ""
        artist = state.get("artist", "") or ""
        if artist and artist not in title:
            return artist
        elif title:
            return title
        else:
            return "Radio"
        

    def get_albumart(self, url):
        """
        Download and return an Image object from the given album art URL.
        If no URL is provided or downloading fails, load the default album art
        specified in the display configuration.
        """
        # If no URL is provided, try to load the default album art.
        if not url:
            default_path = self.display_manager.config.get("default_album_art")
            if default_path and os.path.exists(default_path):
                try:
                    img = Image.open(default_path)
                    return img.convert("RGB")
                except Exception as e:
                    self.logger.error(f"Failed to load default album art from {default_path}: {e}")
                    return None
            else:
                self.logger.error("No album art URL provided and default album art not found.")
                return None

        # Attempt to download the album art.
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            return img.convert("RGB")
        except Exception as e:
            self.logger.error(f"Failed to load album art from {url}: {e}")
            # Fallback to default album art if download fails.
            default_path = self.display_manager.config.get("default_album_art")
            if default_path and os.path.exists(default_path):
                try:
                    img = Image.open(default_path)
                    return img.convert("RGB")
                except Exception as e:
                    self.logger.error(f"Failed to load default album art from {default_path}: {e}")
                    return None
            return None


    def display_radioplayback_info(self):
        """
        If needed, manually refresh the display with the current state.
        """
        if not self.is_active:
            self.logger.info("WebRadioScreen: display_radioplayback_info called, but mode is not active.")
            return

        state = self.volumio_listener.get_current_state()
        if state:
            self.draw_display(state)
        else:
            self.logger.warning("WebRadioScreen: No current volumio state available to display.")

    # ------------------------------------------------------------------
    # Spectrum FIFO (vertical bars in a restricted region)
    # ------------------------------------------------------------------
    def _draw_spectrum(self, draw):
        """
        Draw vertical bar spectrum from self.spectrum_bars in a restricted region
        on the left side so it doesn't overlap the album art.
        """
        screen_width, screen_height = self.display_manager.oled.size

        # Use consistent values:
        margin = 20
        album_art_width = 60     # same as used for album art
        extra_margin = 25        # extra space between spectrum and album art

        region_left = margin
        region_right = screen_width - album_art_width - extra_margin
        region_width = region_right - region_left

        # Define vertical placement of the spectrum region.
        region_top = 38          # e.g., below the station title and info
        region_height = 20       # Height of the spectrum region
        region_bottom = region_top + region_height

        # If spectrum is disabled or no data is available, clear only this region.
        if (not self.running_spectrum) or (not self.mode_manager.config.get("cava_enabled", False)):
            draw.rectangle([region_left, region_top, region_right, region_bottom], fill="black")
            return

        bars = self.spectrum_bars
        num_bars = len(bars)
        if num_bars < 1:
            return

        # Set fixed bar width and gap.
        bar_width = 2
        gap_width = 3
        total_bars_width = num_bars * (bar_width + gap_width) - gap_width

        # Center the bars within the region.
        start_x = region_left + (region_width - total_bars_width) // 2
        max_height = region_height

        for i, bar in enumerate(bars):
            bar_val = max(0, min(bar, 255))
            bar_height = int((bar_val / 255.0) * max_height)
            x1 = start_x + i * (bar_width + gap_width)
            x2 = x1 + bar_width
            y1 = region_bottom - bar_height
            y2 = region_bottom
            draw.rectangle([x1, y1, x2, y2], fill="#303030")

    # ------------------------------------------------------------------
    # Drawing the Screen
    # ------------------------------------------------------------------
    def draw_display(self, data):
        """
        Render a webradio screen with a layout similar to the minimal screen:
         - Station title (truncated if needed) on the top-left.
         - Info text (volume, "WebRadio", and bitrate/Live) underneath the title.
           When the spectrum is off, the info text is moved further down.
         - Station album art on the right.
         - Optional vertical bar spectrum drawn in a restricted region on the left.
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)
        screen_width, screen_height = self.display_manager.oled.size
        margin = 5

        # Define album art width (should be the same everywhere)
        album_art_width = 50  
        available_width = screen_width - album_art_width - (2 * margin)

        # 1) Draw the station (or title) text using font_station.
        station_text = self.get_display_text(data)
        max_chars = 25
        if len(station_text) > max_chars:
            station_text = station_text[:max_chars] + "..."
        station_x = margin
        station_y = margin
        draw.text((station_x, station_y), station_text, font=self.font_station, fill="white")
        
        # Use a fixed title height to keep spacing consistent.
        fixed_title_height = 15

        # 2) Build and draw the info text (volume, "WebRadio", and bitrate/Live).
        info_text = ""
        if data.get("volume") is not None:
            info_text += f"Vol: {data.get('volume')}"
        if info_text:
            info_text += " | "
        info_text += "WebRadio"
        bitrate = data.get("bitrate")
        if bitrate:
            info_text += " | " + bitrate
        else:
            info_text += " | Live"
        
        # Calculate the info text y-position.
        info_y = station_y + fixed_title_height + 5
        # When spectrum is off, push the info text further down.
        if not self.mode_manager.config.get("cava_enabled", False):
            info_y += 15  # extra offset when spectrum is off
        info_x = margin
        
        draw.text((info_x, info_y), info_text, font=self.font_label, fill="white")

        # 3) Display the station's album art on the right.
        albumart_url = data.get("albumart")
        if albumart_url:
            albumart = self.get_albumart(albumart_url)
            if albumart:
                album_art_size = (album_art_width, album_art_width)
                albumart = albumart.resize(album_art_size, Image.LANCZOS)
                art_x = screen_width - album_art_size[0] - margin
                art_y = margin
                base_image.paste(albumart, (art_x, art_y))

        # 4) Draw the vertical bar spectrum (or clear its region) in a restricted area on the left.
        if self.mode_manager.config.get("cava_enabled", False):
            # Use the same region parameters as in your _draw_spectrum.
            self._draw_spectrum(draw)
        else:
            # Clear only the spectrum region without affecting the info text.
            # We'll use the same horizontal boundaries as in _draw_spectrum:
            extra_margin = 25
            region_left = margin
            region_right = screen_width - album_art_width - extra_margin
            # For vertical placement, we place the spectrum region just below the info text.
            # We can measure an approximate info text height (or use a fixed value).
            _, sample_info_h = self.font_label.getsize("Vol: 100 | WebRadio | Live")
            region_top = info_y + sample_info_h + 2  # 2 pixels below the info text
            region_height = 25  # set the height of the spectrum region
            draw.rectangle([region_left, region_top, region_right, region_top + region_height], fill="black")

        # 5) Display the final composed image.
        self.display_manager.oled.display(base_image)
        self.logger.debug("WebRadioScreen: Display updated with webradio UI (minimal layout).")
