import logging
import os
import threading
import time
import math
from PIL import Image, ImageDraw, ImageFont
from managers.menus.base_manager import BaseManager

FIFO_PATH = "/tmp/vumeter.fifo"  # Path to the FIFO for CAVA data

class VUMeterScreen(BaseManager):
    """
    A screen class for displaying a VU meter background plus
    real-time overlay from CAVA data (via /tmp/vumeter.fifo).
    Also draws track info & a service icon at the bottom.
    """

    def __init__(
        self,
        display_manager,
        volumio_listener,
        mode_manager,
        vu_path=""
    ):
        super().__init__(display_manager, volumio_listener, mode_manager)

        self.logger = logging.getLogger(type(self).__name__)
        self.logger.setLevel(logging.DEBUG)

        # Basic references
        self.mode_manager     = mode_manager
        self.volumio_listener = volumio_listener
        self.vu_path          = vu_path

        # CAVA logic
        self.running_spectrum = False
        self.spectrum_thread  = None
        self.spectrum_bars    = []

        # Fonts
        self.font_data = self.display_manager.fonts.get('data_font', ImageFont.load_default())

        # Threaded update logic
        self.latest_state  = None
        self.current_state = None
        self.state_lock    = threading.Lock()
        self.update_event  = threading.Event()
        self.stop_event    = threading.Event()
        self.is_active     = False

        # For a background image, we’ll store it after the first load
        self.cached_vu_bg  = None

        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("VUMeterScreen: Created background update thread.")

        # Connect to VolumioListener
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)

        # ------------------------------------------------------------------
        # Needle images
        # ------------------------------------------------------------------
        self.needle_left_path  = "/home/volumio/Quadify/src/assets/images/needle_left.png"
        self.needle_right_path = "/home/volumio/Quadify/src/assets/images/needle_right.png"
        
        # Local pivot inside your needle images
        self.needle_local_pivot = (50, 73)

        # Screen pivots (where we “pin” the needle on the background)
        self.needle_left_screen_pivot  = (65, 56)
        self.needle_right_screen_pivot = (189, 56)

        # We’ll load these needle images in start_mode
        self.needle_left_img  = None
        self.needle_right_img = None

        # Angle range
        self.min_angle_degrees = -50
        self.max_angle_degrees = 50

        # Optional icons for Tidal, Qobuz, etc.
        self.service_icons = {}  

        self.logger.info("VUMeterScreen: Initialized successfully.")

    # ------------------------------------------------------------------
    #   Volumio State Changes
    # ------------------------------------------------------------------
    def on_volumio_state_change(self, sender, state):
        """
        Called whenever Volumio's pushState arrives.
        Update and redraw only if we are active & in vumeterscreen mode.
        """
        if not self.is_active:
            self.logger.debug("VUMeterScreen: ignoring state change (inactive).")
            return

        if self.mode_manager.get_mode() != 'vumeterscreen':
            self.logger.debug("VUMeterScreen: ignoring state change (mode != vumeterscreen).")
            return

        old_status = self.current_state["status"] if self.current_state else None
        new_status = state.get("status", None)

        self.logger.info(
            f"VUMeterScreen: Volumio state changed from '{old_status}' to '{new_status}' "
            f"({state.get('trackType','?')} / {state.get('bitdepth','?')} / {state.get('samplerate','?')})"
        )

        with self.state_lock:
            self.latest_state = state
        self.update_event.set()

    # ------------------------------------------------------------------
    #   Background Update Thread
    # ------------------------------------------------------------------
    def update_loop(self):
        """
        Continuously wait for new state updates or a timeout,
        then re-draw if we're active in 'vumeterscreen'.
        """
        last_update = time.time()

        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            if triggered:
                with self.state_lock:
                    if self.latest_state:
                        self.current_state = self.latest_state.copy()
                        self.latest_state  = None
                        self.update_event.clear()
                        last_update = time.time()
                    elif (self.current_state 
                          and "seek" in self.current_state 
                          and "duration" in self.current_state):
                        # Optionally increment 'seek' to keep time
                        elapsed = time.time() - last_update
                        self.current_state["seek"] += int(elapsed * 1000)
                        last_update = time.time()

            # If active + correct mode => draw
            if self.is_active and (self.mode_manager.get_mode() == 'vumeterscreen'):
                if self.current_state:
                    self.draw_screen(self.current_state)

    # ------------------------------------------------------------------
    #   Start / Stop Methods
    # ------------------------------------------------------------------
    def start_mode(self):
        """
        Called when we enter vumeterscreen mode from ModeManager.
        """
        if self.mode_manager.get_mode() != 'vumeterscreen':
            self.logger.warning("VUMeterScreen: Attempted to start, but mode != 'vumeterscreen'.")
            return

        self.is_active = True

        # Load needle images if needed
        if not self.needle_left_img and os.path.exists(self.needle_left_path):
            self.needle_left_img = Image.open(self.needle_left_path).convert("RGBA")

        if not self.needle_right_img and os.path.exists(self.needle_right_path):
            self.needle_right_img = Image.open(self.needle_right_path).convert("RGBA")

        # Load background once, if not loaded
        self._load_vu_background_into_cache()

        # Start reading CAVA data if not already
        if not self.spectrum_thread or not self.spectrum_thread.is_alive():
            self.running_spectrum = True
            self.spectrum_thread = threading.Thread(target=self._read_fifo, daemon=True)
            self.spectrum_thread.start()
            self.logger.info("VUMeterScreen: CAVA reading thread started.")

        # Immediately fetch or draw the current state
        if self.volumio_listener:
            current_state = self.volumio_listener.get_current_state()
            if current_state:
                self.logger.debug("VUMeterScreen: Drawing screen with current Volumio state.")
                with self.state_lock:
                    self.current_state = current_state.copy()
                self.draw_screen(self.current_state)
            else:
                # If we have no known state, request from Volumio
                self.logger.debug("VUMeterScreen: No cached state => requesting getState from Volumio.")
                try:
                    self.volumio_listener.socketIO.emit("getState", {})
                except Exception as e:
                    self.logger.error(f"VUMeterScreen: Failed to emit getState => {e}")
                
                # Optionally do an empty draw so user sees at least background + needles
                self.logger.debug("VUMeterScreen: Drawing screen with empty state while we wait.")
                self.draw_screen({})
        else:
            # If no Volumio listener at all, just do an empty draw
            self.draw_screen({})

    def stop_mode(self):
        """
        Called when leaving vumeterscreen mode (e.g. going back to clock mode).
        """
        if not self.is_active:
            self.logger.debug("VUMeterScreen: stop_mode called but already inactive.")
            return

        self.is_active = False
        self.update_event.set()

        self.running_spectrum = False
        if self.spectrum_thread and self.spectrum_thread.is_alive():
            self.spectrum_thread.join(timeout=1)
            self.logger.info("VUMeterScreen: CAVA thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("VUMeterScreen: Stopped and cleared screen.")

    # ------------------------------------------------------------------
    #   Reading from /tmp/vumeter.fifo (CAVA data)
    # ------------------------------------------------------------------
    def _read_fifo(self):
        """
        Open the FIFO and continuously read lines from CAVA.
        We log only once every 100 lines to prevent spam.
        """
        if not os.path.exists(FIFO_PATH):
            self.logger.error(f"VUMeterScreen: FIFO '{FIFO_PATH}' not found.")
            return

        self.logger.debug(f"VUMeterScreen: reading from {FIFO_PATH}")
        line_count = 0
        try:
            with open(FIFO_PATH, "r") as fifo:
                while self.running_spectrum:
                    line = fifo.readline().strip()
                    if not line:
                        continue
                    bars = [int(x) for x in line.split(";") if x.isdigit()]
                    self.spectrum_bars = bars

                    line_count += 1
                    if line_count % 100 == 0:
                        self.logger.debug(f"VUMeterScreen: Still reading CAVA data... ({line_count} lines processed)")
        except Exception as e:
            self.logger.error(f"VUMeterScreen: error reading from FIFO => {e}")

    # ------------------------------------------------------------------
    #   Main Drawing Methods
    # ------------------------------------------------------------------
    def draw_screen(self, state_data):
        """
        Main rendering entry point.
        1) Start with a new RGBA base image
        2) Paste the cached background (if any)
        3) Draw needles based on CAVA data
        4) Draw track info
        5) Convert to RGB & display
        """
        base_img = Image.new("RGBA", self.display_manager.oled.size, (0,0,0,255))

        # (1) Paste background from cache
        if self.cached_vu_bg:
            base_img.paste(self.cached_vu_bg, (0,0))
        else:
            # fallback if background not available
            base_img = self._draw_vu_background_on_the_fly(base_img)

        # (2) Needles
        self._draw_vu_overlay(base_img)

        # (3) Track info
        self._draw_track_info(base_img, state_data)

        # (4) Display
        final_img = base_img.convert("RGB")
        self.display_manager.oled.display(final_img)

        self.logger.debug("VUMeterScreen: Display updated with new data.")

    def _load_vu_background_into_cache(self):
        """
        Load & resize the VU background once, store in self.cached_vu_bg.
        """
        if not self.vu_path:
            self.logger.debug("VUMeterScreen: No vu_path specified => no background caching.")
            return

        if not os.path.exists(self.vu_path):
            self.logger.error(f"VUMeterScreen: '{self.vu_path}' not found!")
            return

        try:
            vu_img = Image.open(self.vu_path)
            if vu_img.mode == "RGBA":
                bg = Image.new("RGB", vu_img.size, "black")
                bg.paste(vu_img, mask=vu_img.split()[3])
                vu_img = bg

            w, h = self.display_manager.oled.size
            vu_img = vu_img.resize((w, h), Image.LANCZOS)
            self.cached_vu_bg = vu_img
            self.logger.debug(f"VUMeterScreen: Cached VU background => size {vu_img.size}, mode {vu_img.mode}")
        except IOError as e:
            self.logger.error(f"VUMeterScreen: Failed to open VU image => {e}")

    def _draw_vu_background_on_the_fly(self, base_img):
        """
        If we didn't cache the VU image, do a one-time load here.
        Not recommended in a tight loop, but as fallback.
        """
        if not self.vu_path or not os.path.exists(self.vu_path):
            # no background path => just keep black
            return base_img

        try:
            vu_img = Image.open(self.vu_path)
            if vu_img.mode == "RGBA":
                bg = Image.new("RGB", vu_img.size, "black")
                bg.paste(vu_img, mask=vu_img.split()[3])
                vu_img = bg
            w, h = self.display_manager.oled.size
            vu_img = vu_img.resize((w, h), Image.LANCZOS)
            base_img.paste(vu_img, (0,0))
            return base_img
        except IOError as e:
            self.logger.error(f"VUMeterScreen: Failed to open VU image => {e}")
            return base_img

    def _draw_vu_overlay(self, base_img):
        """
        Rotate and overlay the left/right needles based on self.spectrum_bars.
        """
        if len(self.spectrum_bars) < 2:
            # Not enough data => no needle movement
            return

        left_val  = self.spectrum_bars[0]
        right_val = self.spectrum_bars[1]

        left_angle  = self._map_value_to_angle(left_val)
        right_angle = self._map_value_to_angle(right_val)

        # Left needle
        if self.needle_left_img:
            rotated_left = self._rotate_needle(
                self.needle_left_img,
                left_angle,
                self.needle_local_pivot
            )
            offset_left = (
                self.needle_left_screen_pivot[0] - self.needle_local_pivot[0],
                self.needle_left_screen_pivot[1] - self.needle_local_pivot[1]
            )
            base_img.paste(rotated_left, offset_left, rotated_left)

        # Right needle
        if self.needle_right_img:
            rotated_right = self._rotate_needle(
                self.needle_right_img,
                right_angle,
                self.needle_local_pivot
            )
            offset_right = (
                self.needle_right_screen_pivot[0] - self.needle_local_pivot[0],
                self.needle_right_screen_pivot[1] - self.needle_local_pivot[1]
            )
            base_img.paste(rotated_right, offset_right, rotated_right)

    def _rotate_needle(self, needle_img, angle_deg, local_pivot):
        """
        Rotate the needle image around local_pivot by angle_deg.
        """
        return needle_img.rotate(
            angle_deg,
            resample=Image.NEAREST,
            expand=False,
            center=local_pivot
        )

    # ------------------------------------------------------------------
    #   Drawing Track Info
    # ------------------------------------------------------------------
    def _draw_track_info(self, base_img, state_data):
        """
        Draw trackType (FLAC), bitdepth & samplerate near the bottom center.
        Example:
           FLAC
           24 bit • 44.1 kHz
        """
        track_type = state_data.get("trackType", "").upper()    
        bitdepth   = state_data.get("bitdepth", "")             
        samplerate = state_data.get("samplerate", "")           

        if not (track_type or bitdepth or samplerate):
            return

        parts = []
        if bitdepth:
            parts.append(bitdepth)
        if samplerate:
            parts.append(samplerate)
        second_line = " • ".join(parts)

        draw = ImageDraw.Draw(base_img)
        display_w, display_h = self.display_manager.oled.size

        line1 = track_type
        line2 = second_line

        line1_w, line1_h = draw.textsize(line1, font=self.font_data)
        line2_w, line2_h = draw.textsize(line2, font=self.font_data)

        margin_between_lines = 1
        total_height = line1_h + line2_h + margin_between_lines

        line2_y = display_h - line2_h - 5
        line1_y = line2_y - (line1_h + margin_between_lines)

        line1_x = (display_w - line1_w) // 2
        line2_x = (display_w - line2_w) // 2

        if track_type:
            draw.text((line1_x, line1_y), line1, fill="white", font=self.font_data)
        if second_line:
            draw.text((line2_x, line2_y), second_line, fill="white", font=self.font_data)

    # ------------------------------------------------------------------
    #   Helpers
    # ------------------------------------------------------------------
    def _map_value_to_angle(self, val_0_255):
        """
        Convert 0..255 bar to an angle between self.min_angle_degrees and self.max_angle_degrees,
        inverting the amplitude so 0 => max angle, 255 => min angle.
        """
        span = self.max_angle_degrees - self.min_angle_degrees
        inverted_val = 255 - val_0_255
        return self.min_angle_degrees + (inverted_val / 255.0) * span

    def display_playback_info(self):
        """
        Convenience method to manually re-draw the screen if you want,
        pulling current state from the listener.
        """
        if not self.volumio_listener:
            return
        state = self.volumio_listener.get_current_state()
        if state:
            self.draw_screen(state)

    def toggle_play_pause(self):
        """
        Example method to show you can integrate playback controls.
        """
        if not self.volumio_listener or not self.volumio_listener.is_connected():
            self.logger.warning("VUMeterScreen: No Volumio connection; cannot toggle play/pause.")
            return
        try:
            self.volumio_listener.socketIO.emit("toggle", {})
            self.logger.info("VUMeterScreen: Emitted 'toggle' for play/pause.")
        except Exception as e:
            self.logger.error(f"VUMeterScreen: toggle_play_pause failed => {e}")
