# src/managers/webradio_manager.py

import os
import logging
from PIL import Image, ImageDraw, ImageFont
import threading
import time

FIFO_PATH = "/tmp/display.fifo"  # Path to the FIFO for CAVA data

class WebRadioScreen:
    """
    A simplified, 'modern-style' WebRadio screen featuring:
      - Single line (station/song) centred at the top
      - 'WebRadio' label under it
      - Optional spectrum (via CAVA FIFO), no progress bar or volume bars
      - Minimal logic around station name vs. title from Volumio
    """

    def __init__(self, display_manager, volumio_listener, mode_manager):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        self.display_manager   = display_manager
        self.volumio_listener  = volumio_listener
        self.mode_manager      = mode_manager

        # State & screen activity
        self.is_active      = False
        self.latest_state   = None
        self.current_state  = None
        self.state_lock     = threading.Lock()
        self.update_event   = threading.Event()
        self.stop_event     = threading.Event()

        # Spectrum / CAVA
        self.running_spectrum = False
        self.spectrum_thread  = None
        self.spectrum_bars    = []

        # Fonts (ensure these exist in display_manager.fonts or define fallback)
        self.font_station = display_manager.fonts.get('radio_title',  ImageFont.load_default())
        self.font_label   = display_manager.fonts.get('radio_bitrate', ImageFont.load_default())

        # Scrolling (optional; remove if you don't want scrolling logic)
        self.scroll_offset_station = 0
        self.scroll_speed          = 2

        # Display update thread
        self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("WebRadioScreen: Started background update thread.")

        # Connect to Volumio listener
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)
        self.logger.info("WebRadioScreen initialized.")

    # ------------------------------------------------------------------
    #   Volumio State Change
    # ------------------------------------------------------------------
    def on_volumio_state_change(self, sender, state):
        """
        Triggered whenever VolumioListener emits a state_changed signal.
        Only update if:
          - self.is_active == True
          - mode_manager.get_mode() == 'webradio'
          - service == 'webradio'
        """
        if not self.is_active:
            self.logger.debug("WebRadioScreen: ignoring state change; screen not active.")
            return

        if self.mode_manager.get_mode() != 'webradio':
            self.logger.debug("WebRadioScreen: ignoring state change; not in webradio mode.")
            return

        if state.get("service") != "webradio":
            self.logger.debug("WebRadioScreen: ignoring state change; service != webradio.")
            return

        self.logger.debug(f"WebRadioScreen: state changed => {state}")
        with self.state_lock:
            self.latest_state = state
        self.update_event.set()

    # ------------------------------------------------------------------
    #   Background Update Loop
    # ------------------------------------------------------------------
    def update_display_loop(self):
        """
        Runs in the background to handle display updates. Waits on update_event
        or times out periodically, so we can animate text or handle the spectrum.
        """
        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            with self.state_lock:
                if triggered and self.latest_state:
                    # We got a new state from Volumio
                    self.current_state = self.latest_state.copy()
                    self.latest_state  = None
                    self.update_event.clear()

            # If active & mode == 'webradio' & we have a current state => draw
            if self.is_active and self.mode_manager.get_mode() == 'webradio' and self.current_state:
                self.draw_display(self.current_state)

    # ------------------------------------------------------------------
    #   Start/Stop
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

        # 1) Force immediate getState from Volumio
        try:
            if self.volumio_listener and self.volumio_listener.socketIO:
                self.logger.debug("WebRadioScreen: Forcing getState from Volumio.")
                self.volumio_listener.socketIO.emit("getState", {})
        except Exception as e:
            self.logger.warning(f"WebRadioScreen: Failed to emit 'getState'. Error => {e}")

        # 2) Only start reading the FIFO if cava_enabled == True
        if self.mode_manager.config.get("cava_enabled", False):
            if not self.spectrum_thread or not self.spectrum_thread.is_alive():
                self.running_spectrum = True
                self.spectrum_thread = threading.Thread(target=self._read_fifo, daemon=True)
                self.spectrum_thread.start()
                self.logger.info("WebRadioScreen: Spectrum reading thread started.")
        else:
            self.logger.info("WebRadioScreen: Spectrum is disabled globally, skipping FIFO reading.")

        # 3) If the update_thread is dead for some reason, restart it
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

        # Stop spectrum thread (if it's running)
        self.running_spectrum = False
        if self.spectrum_thread and self.spectrum_thread.is_alive():
            self.spectrum_thread.join(timeout=1)
            self.logger.info("WebRadioScreen: Spectrum thread stopped.")

        # Stop update thread
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
            self.logger.debug("WebRadioScreen: display update thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("WebRadioScreen: Stopped mode and cleared screen.")

    # ------------------------------------------------------------------
    #   Spectrum FIFO
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
    #   Scrolling
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
    #   Drawing the screen
    # ------------------------------------------------------------------
    def draw_display(self, data):
        """
        Render webradio screen with:
          - Station/Title text (centre)
          - 'WebRadio' label
          - Optional spectrum at the bottom
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)

        # Extract station text
        station_text = self.get_display_text(data)

        screen_width, screen_height = self.display_manager.oled.size
        margin = 5
        max_text_width = screen_width - 2 * margin

        # 1) Scroll or centre the top line
        station_disp, self.scroll_offset_station, scrolling = self.update_scroll(
            station_text, self.font_station, max_text_width, self.scroll_offset_station
        )
        if scrolling:
            text_x = (screen_width // 2) - self.scroll_offset_station
        else:
            text_w, _ = self.font_station.getsize(station_disp)
            text_x = (screen_width - text_w) // 2

        text_y = 8  # tweak as desired
        draw.text((text_x, text_y), station_disp, font=self.font_station, fill="white")

        # 2) "WebRadio" line, also centred
        label_text = "WebRadio"
        label_w, _ = self.font_label.getsize(label_text)
        label_x = (screen_width - label_w) // 2
        label_y = text_y + 20  # space it below the station text
        draw.text((label_x, label_y), label_text, font=self.font_label, fill="white")

        # 3) Spectrum at the bottom
        self._draw_spectrum(draw)

        # Show final image
        self.display_manager.oled.display(base_image)
        self.logger.debug("WebRadioScreen: Display updated with webradio UI.")

    def _draw_spectrum(self, draw):
        """
        Draw vertical bar spectrum from self.spectrum_bars
        if cava_enabled is True. Otherwise, fill black.
        """
        width, height = self.display_manager.oled.size
        bar_region_height = height // 3
        vertical_offset   = height - bar_region_height

        # If global spectrum is disabled or we didn't start the thread, fill black
        if (not self.running_spectrum) or (not self.mode_manager.config.get("cava_enabled", False)):
            draw.rectangle([0, vertical_offset, width, height], fill="black")
            return

        # Draw bars from self.spectrum_bars
        bars = self.spectrum_bars
        bar_width = 2
        gap_width = 5
        max_height = bar_region_height
        start_x = (width - (len(bars) * (bar_width + gap_width))) // 2

        for i, bar in enumerate(bars):
            bar_val = max(0, min(bar, 255))
            bar_h = int((bar_val / 255.0) * max_height)

            x1 = start_x + i * (bar_width + gap_width)
            x2 = x1 + bar_width
            y1 = height - bar_h
            y2 = height
            draw.rectangle([x1, y1, x2, y2], fill="#303030")

    # ------------------------------------------------------------------
    #   Helpers
    # ------------------------------------------------------------------
    def get_display_text(self, state):
        """
        Decide what text to display based on Volumio's 'title' and 'artist'.
        Some stations only supply 'title' (which might be the station name),
        others supply 'artist' or combine them.
        """
        title  = state.get("title",  "") or ""
        artist = state.get("artist", "") or ""

        # Example logic:
        if artist and artist not in title:
            return artist
        elif title:
            return title
        else:
            return "Radio"

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
