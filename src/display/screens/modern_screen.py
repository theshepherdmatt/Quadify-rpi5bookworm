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
    """

    def __init__(self, display_manager, volumio_listener, mode_manager):
        super().__init__(display_manager, volumio_listener, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        self.mode_manager    = mode_manager
        self.volumio_listener = volumio_listener

        # Spectrum / CAVA
        self.running_spectrum = False
        self.spectrum_thread  = None
        self.spectrum_bars    = []

        # Font references
        self.font_title   = self.display_manager.fonts.get('song_font', ImageFont.load_default())
        self.font_artist  = self.display_manager.fonts.get('artist_font', ImageFont.load_default())
        self.font_info    = self.display_manager.fonts.get('data_font',   ImageFont.load_default())
        self.font_progress= self.display_manager.fonts.get('progress_bar',ImageFont.load_default())

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

            # If active & mode == 'modern', draw
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

        # Start the spectrum reading thread if not already running
        if not self.spectrum_thread or not self.spectrum_thread.is_alive():
            self.running_spectrum = True
            self.spectrum_thread = threading.Thread(target=self._read_fifo, daemon=True)
            self.spectrum_thread.start()
            self.logger.info("ModernScreen: Spectrum reading thread started.")

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
          - Spectrum bars
          - Artist/title with scrolling
          - Progress bar
          - Volume & track info
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)

        # 1) Draw spectrum
        self._draw_spectrum(draw)

        # 2) Extract data from Volumio state
        song_title = data.get("title",  "Unknown Title")
        artist_name= data.get("artist", "Unknown Artist")
        seek_ms    = data.get("seek",   0)
        duration_s = data.get("duration", 1)
        service    = data.get("service", "default")
        samplerate = data.get("samplerate", "N/A")
        bitdepth   = data.get("bitdepth",   "N/A")
        volume     = data.get("volume",     50)

        # Convert seek => seconds
        seek_s = max(0, seek_ms / 1000)
        progress = max(0.0, min(seek_s / duration_s, 1.0))

        # Time strings
        cur_min = int(seek_s // 60)
        cur_sec = int(seek_s % 60)
        tot_min = int(duration_s // 60)
        tot_sec = int(duration_s % 60)
        current_time   = f"{cur_min}:{cur_sec:02d}"
        total_duration = f"{tot_min}:{tot_sec:02d}"

        # 3) Artist/title scrolling
        screen_width, screen_height = self.display_manager.oled.size
        margin        = 5
        max_text_width= screen_width - 2*margin

        # Artist
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

        # Title
        title_disp, self.scroll_offset_title, title_scrolling = self.update_scroll(
            song_title, self.font_title, max_text_width, self.scroll_offset_title
        )
        if title_scrolling:
            title_x = (screen_width // 2) - self.scroll_offset_title
        else:
            text_w, _ = self.font_title.getsize(title_disp)
            title_x = (screen_width - text_w) // 2
        title_y = margin + 6
        draw.text((title_x, title_y), title_disp, font=self.font_title, fill="white")

        # 4) Info text: e.g. "48kHz / 16bit"
        info_text = f"{samplerate} / {bitdepth}"
        info_w, info_h = self.font_info.getsize(info_text)
        info_x = (screen_width - info_w) // 2
        info_y = margin + 25
        draw.text((info_x, info_y), info_text, font=self.font_info, fill="white")

        # 5) Progress bar
        progress_width = int(screen_width * 0.7)
        progress_x = (screen_width - progress_width) // 2
        progress_y = margin + 55

        # Times
        draw.text((progress_x - 30, progress_y - 9), current_time, font=self.font_info, fill="white")
        draw.text((progress_x + progress_width + 12, progress_y - 9), total_duration, font=self.font_info, fill="white")

        # Draw the bar
        draw.line([progress_x, progress_y, progress_x + progress_width, progress_y], fill="white", width=1)
        # progress indicator
        indicator_x = progress_x + int(progress_width * progress)
        draw.line([indicator_x, progress_y - 2, indicator_x, progress_y + 2], fill="white", width=1)

        # 6) Volume icon & text
        volume_icon = self.display_manager.icons.get('volume', self.display_manager.default_icon)
        if volume_icon:
            volume_icon = volume_icon.resize((10, 10), Image.LANCZOS)
        vol_icon_x = progress_x - 30
        vol_icon_y = progress_y - 22
        base_image.paste(volume_icon, (vol_icon_x, vol_icon_y))
        vol_text_x  = vol_icon_x + 12
        vol_text_y  = vol_icon_y - 2
        draw.text((vol_text_x, vol_text_y), str(volume), font=self.font_info, fill="white")

        # Show final
        self.display_manager.oled.display(base_image)
        self.logger.debug("ModernScreen: Display updated with 'modern' playback UI.")


    def _draw_spectrum(self, draw):
        """
        Simple vertical bar spectrum from self.spectrum_bars.
        For example, if each bar in range 0..255 => scale to half screen.
        """
        bars = self.spectrum_bars
        width, height = self.display_manager.oled.size
        bar_width  = 2
        gap_width  = 3
        max_height = height // 2
        start_x    = (width - (len(bars) * (bar_width + gap_width))) // 2
        vertical_offset = -8  # shift upward if needed

        for i, bar in enumerate(bars):
            bar_val = max(0, min(bar, 255))
            bar_h   = int((bar_val / 255.0) * max_height)
            x1      = start_x + i * (bar_width + gap_width)
            x2      = x1 + bar_width
            y1      = height - bar_h + vertical_offset
            y2      = height + vertical_offset
            draw.rectangle([x1, y1, x2, y2], fill="#303030")


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
