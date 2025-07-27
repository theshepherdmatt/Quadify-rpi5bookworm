# src/display/screens/modern_screen.py

import logging
import os
import re
import threading
import time
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from managers.menus.base_manager import BaseManager

FIFO_PATH = "/tmp/display.fifo"  # Path to the FIFO for CAVA data

class ModernScreen(BaseManager):
    """
    A 'Modern' or 'Detailed' playback screen, featuring:
      - Artist & Title scrolling
      - Spectrum visualization (via CAVA FIFO)
      - Progress bar
      - Volume and track info
      - Service icon (Tidal, Qobuz, etc.)
    """

    def __init__(self, display_manager, volumio_listener, mode_manager):
        super().__init__(display_manager, volumio_listener, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        self.mode_manager     = mode_manager
        self.volumio_listener = volumio_listener

        # Spectrum / CAVA
        self.running_spectrum = False
        self.spectrum_thread  = None
        self.spectrum_bars    = []
        self.spectrum_mode = "bars"  # or "dots", "scope"
        self.spectrum_mode = self.mode_manager.config.get("modern_spectrum_mode", "bars")

        # Font references
        self.font_title    = display_manager.fonts.get('song_font', ImageFont.load_default())
        self.font_artist   = display_manager.fonts.get('artist_font', ImageFont.load_default())
        self.font_info     = display_manager.fonts.get('data_font',   ImageFont.load_default())
        self.font_progress = display_manager.fonts.get('progress_bar',ImageFont.load_default())

        # Scrolling
        self.scroll_offset_title  = 0
        self.scroll_offset_artist = 0
        self.scroll_speed         = 2  # Adjust for faster or slower horizontal scrolling

        # State & threads
        self.latest_state    = None
        self.current_state   = None
        self.state_lock      = threading.Lock()
        self.update_event    = threading.Event()
        self.stop_event      = threading.Event()
        self.is_active       = False

        # Keep track of the last-known service so if we pause/stop, we can still show the same icon
        self.previous_service = None

        # Display update thread
        self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("ModernScreen: Started background update thread.")

        # Connect to Volumio listener
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)
        self.logger.info("ModernScreen initialized.")


    # ------------------------------------------------------------------
    #   Volumio State Change
    # ------------------------------------------------------------------
    def on_volumio_state_change(self, sender, state):
        """
        Called whenever VolumioListener emits a state_changed signal.
        Only update if:
          - self.is_active == True
          - mode_manager.get_mode() == 'modern'
        """
        if not self.is_active or self.mode_manager.get_mode() != 'modern':
            self.logger.debug("ModernScreen: ignoring state change; not active or mode != 'modern'.")
            return

        self.logger.debug(f"ModernScreen: state changed => {state}")
        with self.state_lock:
            self.latest_state = state
        self.update_event.set()

    # ------------------------------------------------------------------
    #   Background Update Loop
    # ------------------------------------------------------------------
    def update_display_loop(self):
        """
        Runs in the background to handle display updates. Waits on update_event
        or times out, so we can animate the progress bar or scrolling text.
        """
        last_update_time = time.time()
        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            with self.state_lock:
                if triggered and self.latest_state:
                    # We got a new state from Volumio
                    self.current_state = self.latest_state.copy()
                    self.latest_state  = None
                    self.update_event.clear()
                    last_update_time = time.time()
                elif self.current_state and "seek" in self.current_state and "duration" in self.current_state:
                    # If we have a playing track, let's simulate progress
                    elapsed = time.time() - last_update_time
                    self.current_state["seek"] = self.current_state.get("seek", 0) + int(elapsed * 1000)
                    last_update_time = time.time()

            # If active & mode == 'modern' and we have a current state, let's draw
            if self.is_active and self.mode_manager.get_mode() == 'modern' and self.current_state:
                self.logger.debug("ModernScreen: drawing updated display.")
                self.draw_display(self.current_state)

    # ------------------------------------------------------------------
    #   Start/Stop
    # ------------------------------------------------------------------
    def start_mode(self):
        """
        Called when ModeManager transitions to 'modern' mode.
        """
        if self.mode_manager.get_mode() != 'modern':
            self.logger.warning("ModernScreen: Attempted start, but mode != 'modern'.")
            return

        self.is_active = True
        self.reset_scrolling()
        self.spectrum_mode = self.mode_manager.config.get("modern_spectrum_mode", "bars")

        # 1) Force an immediate getState
        try:
            if self.volumio_listener and self.volumio_listener.socketIO:
                self.logger.debug("ModernScreen: Forcing getState from Volumio.")
                self.volumio_listener.socketIO.emit("getState", {})
        except Exception as e:
            self.logger.warning(f"ModernScreen: Failed to emit 'getState'. Error => {e}")

        # 2) Start the spectrum reading thread if not already running
        if not self.spectrum_thread or not self.spectrum_thread.is_alive():
            self.running_spectrum = True
            self.spectrum_thread = threading.Thread(target=self._read_fifo, daemon=True)
            self.spectrum_thread.start()
            self.logger.info("ModernScreen: Spectrum reading thread started.")

        # 3) If the update_thread is not alive, restart it
        if not self.update_thread.is_alive():
            self.stop_event.clear()
            self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
            self.update_thread.start()
            self.logger.debug("ModernScreen: display update thread restarted.")


    def stop_mode(self):
        """
        Called when leaving 'modern' mode in ModeManager.
        """
        if not self.is_active:
            self.logger.debug("ModernScreen: stop_mode called but not active.")
            return

        self.is_active = False
        self.stop_event.set()
        self.update_event.set()

        # Stop spectrum thread
        self.running_spectrum = False
        if self.spectrum_thread and self.spectrum_thread.is_alive():
            self.spectrum_thread.join(timeout=1)
            self.logger.info("ModernScreen: Spectrum thread stopped.")

        # Stop update thread
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
            self.logger.debug("ModernScreen: display update thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("ModernScreen: Stopped mode and cleared screen.")

    # ------------------------------------------------------------------
    #   Spectrum FIFO
    # ------------------------------------------------------------------
    def _read_fifo(self):
        """
        Continuously read from the CAVA FIFO and store the bars
        in self.spectrum_bars.
        """
        if not os.path.exists(FIFO_PATH):
            self.logger.error(f"ModernScreen: FIFO {FIFO_PATH} not found.")
            return

        self.logger.debug("ModernScreen: reading from FIFO for spectrum data.")
        try:
            with open(FIFO_PATH, "r") as fifo:
                while self.running_spectrum:
                    line = fifo.readline().strip()
                    if line:
                        bars = [int(x) for x in line.split(";") if x.isdigit()]
                        self.spectrum_bars = bars
        except Exception as e:
            self.logger.error(f"ModernScreen: error reading FIFO => {e}")

    # ------------------------------------------------------------------
    #   Scroll & Volume
    # ------------------------------------------------------------------
    def reset_scrolling(self):
        """ Reset scrolling offsets for artist/title text. """
        self.logger.debug("ModernScreen: resetting scroll offsets.")
        self.scroll_offset_title  = 0
        self.scroll_offset_artist = 0

    def update_scroll(self, text, font, max_width, scroll_offset):
        """
        Basic continuous scrolling logic:
          - If text fits in max_width => no scroll
          - Else increment scroll_offset => wrap around
        """
        text_width, _ = font.getsize(text)
        if text_width <= max_width:
            return text, 0, False

        scroll_offset += self.scroll_speed
        if scroll_offset > text_width:
            scroll_offset = 0

        return text, scroll_offset, True

    def adjust_volume(self, volume_change):
        """
        Adjust volume from an external call (e.g. rotary). This
        emits a volume +/- to Volumio.
        """
        if not self.volumio_listener:
            self.logger.error("ModernScreen: no volumio_listener, cannot adjust volume.")
            return

        if self.latest_state is None:
            self.logger.debug("ModernScreen: latest_state=None => assume volume=100.")
            self.latest_state = {"volume": 100}

        with self.state_lock:
            curr_vol = self.latest_state.get("volume", 100)
            new_vol  = max(0, min(int(curr_vol) + volume_change, 100))

        self.logger.info(f"ModernScreen: Adjusting volume from {curr_vol} to {new_vol}.")
        try:
            if volume_change > 0:
                self.volumio_listener.socketIO.emit("volume", "+")
            elif volume_change < 0:
                self.volumio_listener.socketIO.emit("volume", "-")
            else:
                self.volumio_listener.socketIO.emit("volume", new_vol)
        except Exception as e:
            self.logger.error(f"ModernScreen: error adjusting volume => {e}")

    # ------------------------------------------------------------------
    #   Drawing the screen
    # ------------------------------------------------------------------
    def draw_display(self, data):
        """
        Render 'modern' playback screen with:
        - Spectrum bars (optional)
        - Artist/title with scrolling
        - Progress bar
        - Volume & track info
        - Smaller service icon at bottom-right, near total duration
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)

        # Check if spectrum is actually enabled (both thread running & config set)
        spectrum_enabled = (
            self.running_spectrum and
            self.mode_manager.config.get("cava_enabled", False)
        )

        #
        # 1) Possibly override 'service' if trackType says Tidal/Qobuz
        #
        service  = data.get("service", "default").lower()
        track_type = data.get("trackType", "").lower()
        status   = data.get("status", "").lower()

        if service == "mpd" and track_type in ["tidal", "qobuz", "spotify", "radio_paradise"]:
            service = track_type

        if status in ["pause", "stop"] and not service:
            service = self.previous_service or "default"
        else:
            if service and service != self.previous_service:
                self.logger.info(f"ModernScreen: Service changed => {service}")
            self.previous_service = service or self.previous_service or "default"

        #
        # 2) Draw the spectrum (if enabled)
        #
        self._draw_spectrum(draw)

        #
        # 3) Data from Volumio state
        #
        song_title = data.get("title",  "Unknown Title")
        artist_name= data.get("artist", "Unknown Artist")
        seek_ms    = data.get("seek",   0)
        duration_s = data.get("duration", 1)
        samplerate = data.get("samplerate", "N/A")
        bitdepth   = data.get("bitdepth",   "N/A")
        volume     = data.get("volume",     50)

        # Convert seek => seconds, clamp progress to [0..1]
        seek_s = max(0, seek_ms / 1000)
        progress = max(0.0, min(seek_s / duration_s, 1.0))

        # Times
        cur_min = int(seek_s // 60)
        cur_sec = int(seek_s % 60)
        tot_min = int(duration_s // 60)
        tot_sec = int(duration_s % 60)
        current_time   = f"{cur_min}:{cur_sec:02d}"
        total_duration = f"{tot_min}:{tot_sec:02d}"

        #
        # 4) Artist/title scrolling
        #
        screen_width, screen_height = self.display_manager.oled.size
        margin        = 5
        max_text_width= screen_width - 2 * margin

        # We'll shift the TITLE and INFO text if the spectrum is OFF
        line_shift = 4 if not spectrum_enabled else 0

        # Artist (no shift)
        artist_disp, self.scroll_offset_artist, artist_scrolling = self.update_scroll(
            artist_name, self.font_artist, max_text_width, self.scroll_offset_artist
        )
        if artist_scrolling:
            artist_x = (screen_width // 2) - self.scroll_offset_artist
        else:
            text_w, _ = self.font_artist.getsize(artist_disp)
            artist_x = (screen_width - text_w) // 2

        artist_y = margin - 8
        draw.text((artist_x, artist_y), artist_disp, font=self.font_artist, fill="white")

        # Title (shift if no spectrum)
        title_disp, self.scroll_offset_title, title_scrolling = self.update_scroll(
            song_title, self.font_title, max_text_width, self.scroll_offset_title
        )
        if title_scrolling:
            title_x = (screen_width // 2) - self.scroll_offset_title
        else:
            text_w, _ = self.font_title.getsize(title_disp)
            title_x = (screen_width - text_w) // 2

        title_y = (margin + 6) + line_shift
        draw.text((title_x, title_y), title_disp, font=self.font_title, fill="white")

        #
        # 5) Info text: e.g. "48kHz / 16bit" (also shifted if no spectrum)
        #
        info_text = f"{samplerate} / {bitdepth}"
        info_w, info_h = self.font_info.getsize(info_text)
        info_x = (screen_width - info_w) // 2
        info_y = (margin + 25) + line_shift
        draw.text((info_x, info_y), info_text, font=self.font_info, fill="white")

        #
        # 6) Progress bar + times (no shift)
        #
        progress_width = int(screen_width * 0.7)
        progress_x = (screen_width - progress_width) // 2
        progress_y = margin + 55

        # Current time (left)
        draw.text((progress_x - 30, progress_y - 9), current_time, 
                font=self.font_info, fill="white")

        # Total duration (right)
        dur_x = progress_x + progress_width + 12
        dur_y = progress_y - 9
        draw.text((dur_x, dur_y), total_duration, 
                font=self.font_info, fill="white")

        # Draw main progress line
        draw.line([progress_x, progress_y, progress_x + progress_width, progress_y],
                fill="white", width=1)
        # Progress indicator
        indicator_x = progress_x + int(progress_width * progress)
        draw.line([indicator_x, progress_y - 2, indicator_x, progress_y + 2],
                fill="white", width=1)

        #
        # 7) Volume icon & text
        #
        volume_icon = self.display_manager.icons.get('volume', self.display_manager.default_icon)
        if volume_icon:
            volume_icon = volume_icon.resize((10, 10), Image.LANCZOS)
        vol_icon_x = progress_x - 30
        vol_icon_y = progress_y - 22
        base_image.paste(volume_icon, (vol_icon_x, vol_icon_y))

        vol_text_x  = vol_icon_x + 12
        vol_text_y  = vol_icon_y - 2
        draw.text((vol_text_x, vol_text_y), str(volume), font=self.font_info, fill="white")

        #
        # 8) Place a smaller service icon near total_duration
        #
        icon = self.display_manager.icons.get(service)
        if icon:
            # Flatten alpha if needed
            if icon.mode == "RGBA":
                bg = Image.new("RGB", icon.size, (0, 0, 0))
                bg.paste(icon, mask=icon.split()[3])
                icon = bg

            # Resize the icon
            icon = icon.resize((20, 20), Image.LANCZOS)

            # Measure total_duration text so we can figure out where to place the icon
            dur_text_w, dur_text_h = draw.textsize(total_duration, font=self.font_info)

            # Example offsets
            manual_offset_x = -20
            manual_offset_y = -20

            icon_x = dur_x + dur_text_w + manual_offset_x
            icon_y = dur_y + manual_offset_y
            base_image.paste(icon, (icon_x, icon_y))

            self.logger.debug(
                f"ModernScreen: Pasted service icon '{service}' at ({icon_x}, {icon_y})."
            )
        else:
            self.logger.debug(f"ModernScreen: No icon found for service='{service}' => skipping icon.")

        #
        # Finally, display
        #
        self.display_manager.oled.display(base_image)
        self.logger.debug("ModernScreen: Display updated with 'modern' playback UI.")


    def _draw_spectrum(self, draw):
        width, height = self.display_manager.oled.size
        bar_region_height = height // 2
        vertical_offset   = -8

        if (not self.running_spectrum) or (not self.mode_manager.config.get("cava_enabled", False)):
            y_top = max(0, vertical_offset)
            y_bottom = min(height, bar_region_height + vertical_offset)
            draw.rectangle([0, y_top, width, y_bottom], fill="black")
            return

        bars = self.spectrum_bars
        n = len(bars)
        if n == 0:
            return

        bar_width  = 2
        gap_width  = 3
        max_height = bar_region_height
        start_x    = (width - (n * (bar_width + gap_width))) // 2

        # ---- Bars ----
        if self.spectrum_mode == "bars":
            for i, bar in enumerate(bars):
                bar_val = max(0, min(bar, 255))
                bar_h   = int((bar_val / 255.0) * max_height)
                x1 = start_x + i * (bar_width + gap_width)
                x2 = x1 + bar_width
                y1 = height - bar_h + vertical_offset
                y2 = height + vertical_offset
                draw.rectangle([x1, y1, x2, y2], fill=(60, 60, 60))

        # ---- Dots ----
        elif self.spectrum_mode == "dots":
            dot_size = 3
            dot_vertical_offset = 10  # Move all dots up by this amount
            for i, bar in enumerate(bars):
                bar_val = max(0, min(bar, 255))
                bar_h = int((bar_val / 255.0) * max_height)
                num_dots = bar_h // (dot_size - 1) if (dot_size - 1) else 1
                x = start_x + i * (bar_width + gap_width)
                for j in range(num_dots):
                    y = (height - dot_vertical_offset) - (j * (dot_size + 1))
                    draw.ellipse([x, y, x + dot_size, y + dot_size], fill=(60, 60, 60))


        # ---- Oscilloscope ----
        elif self.spectrum_mode == "scope":
            scope_data = [int((bar / 255.0) * max_height) for bar in bars]
            y_base = height + vertical_offset
            prev_x = start_x
            prev_y = y_base - scope_data[0]
            for i, val in enumerate(scope_data[1:], 1):
                x = start_x + i * (bar_width + gap_width)
                y = y_base - val
                draw.line([prev_x, prev_y, x, y], fill=(80, 80, 80), width=1)
                prev_x, prev_y = x, y


    # ------------------------------------------------------------------
    #   External Interaction
    # ------------------------------------------------------------------
    def display_playback_info(self):
        """
        If needed, manually refresh the display with the current state.
        """
        state = self.volumio_listener.get_current_state()
        if state:
            self.draw_display(state)
        else:
            self.logger.warning("ModernScreen: No current volumio state available to display.")

    def toggle_play_pause(self):
        """Emit Volumio play/pause toggle if connected."""
        self.logger.info("ModernScreen: Toggling play/pause.")
        if not self.volumio_listener or not self.volumio_listener.is_connected():
            self.logger.warning("ModernScreen: Not connected to Volumio => cannot toggle.")
            return
        try:
            self.volumio_listener.socketIO.emit("toggle", {})
            self.logger.debug("ModernScreen: Emitted 'toggle' event.")
        except Exception as e:
            self.logger.error(f"ModernScreen: toggle_play_pause failed => {e}")