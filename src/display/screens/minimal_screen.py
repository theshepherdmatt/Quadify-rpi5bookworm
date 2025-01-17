# src/display/screens/minimal_screen.py

import logging
import os
import threading
import time
from PIL import Image, ImageDraw, ImageFont
from managers.menus.base_manager import BaseManager

class MinimalScreen(BaseManager):
    """
    A minimalist screen style akin to Hegel’s design:
      - Large volume number on the right
      - Service name (e.g. Tidal, Qobuz) on the left
      - Small sample rate & bit depth text below the service
      - Very minimal, white-on-black layout
    """

    def __init__(self, display_manager, volumio_listener, mode_manager):
        super().__init__(display_manager, volumio_listener, mode_manager)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        self.mode_manager     = mode_manager
        self.volumio_listener = volumio_listener

        # Fonts defined in your config:
        #   minimal_volume   => Montserrat-Bold,   size=27
        #   minimal_service  => Montserrat-Regular, size=18
        #   minimal_data     => Montserrat-Regular, size=5
        self.font_volume  = display_manager.fonts.get('minimal_volume',  ImageFont.load_default())
        self.font_service = display_manager.fonts.get('minimal_service', ImageFont.load_default())
        self.font_data    = display_manager.fonts.get('minimal_data',    ImageFont.load_default())

        # State & threading
        self.latest_state  = None
        self.current_state = None
        self.state_lock    = threading.Lock()
        self.update_event  = threading.Event()
        self.stop_event    = threading.Event()
        self.is_active     = False

        # Display update thread
        self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("MinimalScreen: Started background update thread.")

        # Connect Volumio state listener
        if self.volumio_listener:
            self.volumio_listener.state_changed.connect(self.on_volumio_state_change)
        self.logger.info("MinimalScreen initialized.")

    # ------------------------------------------------------------------
    #   Volumio State Change
    # ------------------------------------------------------------------
    def on_volumio_state_change(self, sender, state):
        """
        Update only if:
          - self.is_active
          - mode_manager.get_mode() == 'minimal'
        """
        if not self.is_active or self.mode_manager.get_mode() != 'minimal':
            self.logger.debug("MinimalScreen: ignoring state change; not active or mode != 'minimal'.")
            return

        self.logger.debug(f"MinimalScreen: state changed => {state}")
        with self.state_lock:
            self.latest_state = state
        self.update_event.set()

    # ------------------------------------------------------------------
    #   Background Update Loop
    # ------------------------------------------------------------------
    def update_display_loop(self):
        """
        Runs in the background, waits on update_event or times out,
        so we can redraw if needed.
        """
        while not self.stop_event.is_set():
            triggered = self.update_event.wait(timeout=0.1)
            with self.state_lock:
                if triggered and self.latest_state:
                    self.current_state = self.latest_state.copy()
                    self.latest_state  = None
                    self.update_event.clear()

            if self.is_active and self.mode_manager.get_mode() == 'minimal' and self.current_state:
                self.draw_display(self.current_state)

    # ------------------------------------------------------------------
    #   Start / Stop
    # ------------------------------------------------------------------
    def start_mode(self):
        """
        Called when ModeManager transitions to 'minimal' mode.
        """
        if self.mode_manager.get_mode() != 'minimal':
            self.logger.warning("MinimalScreen: Attempted start, but mode != 'minimal'.")
            return

        self.is_active = True

        # Force immediate getState (optional) so we’re not waiting on pushState
        try:
            if self.volumio_listener and self.volumio_listener.socketIO:
                self.logger.debug("MinimalScreen: Forcing getState from Volumio.")
                self.volumio_listener.socketIO.emit("getState", {})
        except Exception as e:
            self.logger.warning(f"MinimalScreen: Failed to emit 'getState'. Error => {e}")

        # If update_thread is dead, restart
        if not self.update_thread.is_alive():
            self.stop_event.clear()
            self.update_thread = threading.Thread(target=self.update_display_loop, daemon=True)
            self.update_thread.start()
            self.logger.debug("MinimalScreen: display update thread restarted.")

    def stop_mode(self):
        """
        Called when leaving 'minimal' mode in ModeManager.
        """
        if not self.is_active:
            self.logger.debug("MinimalScreen: stop_mode called but not active.")
            return

        self.is_active = False
        self.stop_event.set()
        self.update_event.set()

        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
            self.logger.debug("MinimalScreen: display update thread stopped.")

        self.display_manager.clear_screen()
        self.logger.info("MinimalScreen: Stopped mode and cleared screen.")

    # ------------------------------------------------------------------
    #   Drawing
    # ------------------------------------------------------------------
    def draw_display(self, state):
        """
        Minimal UI:
        - Left side (but fixed-right alignment for the service + sample text)
        - Right side: volume in large text
        - Black background, white text, Montserrat fonts.
        """
        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw = ImageDraw.Draw(base_image)

        width, height = self.display_manager.oled.size

        # ------------------------------------------------------------------
        # 1) Extract data from Volumio state
        # ------------------------------------------------------------------
        raw_service = state.get("service", "Network").lower()
        track_type  = state.get("trackType", "").lower()

        # If mpd but track_type is tidal/qobuz/spotify => override
        if raw_service == "mpd" and track_type in ["tidal", "qobuz", "spotify"]:
            raw_service = track_type

        service_display = raw_service.title()
        samplerate = state.get("samplerate", "44.1")
        bitdepth   = state.get("bitdepth",  "16bit")
        volume     = state.get("volume",    0)

        # ------------------------------------------------------------------
        # 2) Right-align service + sample text at a fixed X
        # ------------------------------------------------------------------
        # Choose a fixed X coordinate where the right edge of the service text will be
        # Adjust this number so everything fits on your display:
        service_right = 110
        service_y     = 8

        # 2A) Measure the service text
        service_w, service_h = draw.textsize(service_display, font=self.font_service)
        # 2B) The X for the left edge so the text's right edge is at 'service_right'
        service_x = service_right - service_w

        # Draw service text
        draw.text(
            (service_x, service_y),
            service_display,
            font=self.font_service,
            fill="white"
        )

        # 2C) Sample text, also right-aligned to 'service_right'
        sample_text = f"{samplerate} / {bitdepth}"
        sample_w, sample_h2 = draw.textsize(sample_text, font=self.font_data)
        sample_x = service_right - sample_w
        # put it beneath the service text
        sample_y = service_y + service_h + 1

        draw.text(
            (sample_x, sample_y),
            sample_text,
            font=self.font_data,
            fill="white"
        )

        # ------------------------------------------------------------------
        # 3) Right side: volume (large)
        # ------------------------------------------------------------------
        vol_str = str(volume)
        vol_w, vol_h = draw.textsize(vol_str, font=self.font_volume)

        vol_x = width - vol_w - 40  # offset from the right
        vol_y = (height - vol_h) // 5

        draw.text(
            (vol_x, vol_y),
            vol_str,
            font=self.font_volume,
            fill="white"
        )

        # ------------------------------------------------------------------
        # 4) Display
        # ------------------------------------------------------------------
        self.display_manager.oled.display(base_image)
        self.logger.debug("MinimalScreen: Display updated with minimal UI.")




    def display_playback_info(self):
        """
        If needed, manually refresh using the current state from volumio_listener.
        """
        if not self.is_active:
            self.logger.info("MinimalScreen: display_playback_info called, but mode is not active.")
            return

        state = self.volumio_listener.get_current_state()
        if state:
            self.draw_display(state)
        else:
            self.logger.warning("MinimalScreen: No current volumio state available to display.")

    def adjust_volume(self, volume_change):
        """
        Adjust volume from an external call (e.g. rotary).
        This emits a volume +/- to Volumio via self.volumio_listener.
        """
        if not self.volumio_listener:
            self.logger.error("MinimalScreen: no volumio_listener, cannot adjust volume.")
            return

        # If we haven't got an existing state, default to 100
        if self.latest_state is None:
            self.logger.debug("MinimalScreen: latest_state=None => assume volume=100.")
            self.latest_state = {"volume": 100}

        with self.state_lock:
            curr_vol = self.latest_state.get("volume", 100)
            new_vol = max(0, min(int(curr_vol) + volume_change, 100))

        self.logger.info(f"MinimalScreen: Adjusting volume from {curr_vol} to {new_vol}.")
        try:
            if volume_change > 0:
                self.volumio_listener.socketIO.emit("volume", "+")
            elif volume_change < 0:
                self.volumio_listener.socketIO.emit("volume", "-")
            else:
                self.volumio_listener.socketIO.emit("volume", new_vol)
        except Exception as e:
            self.logger.error(f"MinimalScreen: error adjusting volume => {e}")


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