import logging
import os
import json
import threading
import time
import subprocess
from transitions import Machine

class ModeManager:
    """
    A unified ModeManager for Quadify that includes:
      - Display-mode persistence (original/modern)
      - Screensaver & idle logic
      - Additional states for Tidal/Qobuz/Radio/Playlists
      - Possibly a 'boot' or 'systeminfo' state if desired
    """

    states = [
        {'name': 'boot',            'on_enter': 'enter_boot'},
        {'name': 'clock',           'on_enter': 'enter_clock'},
        {'name': 'screensaver',     'on_enter': 'enter_screensaver'},
        {'name': 'screensavermenu', 'on_enter': 'enter_screensavermenu'},
        {'name': 'displaymenu',     'on_enter': 'enter_displaymenu'},
        {'name': 'clockmenu',       'on_enter': 'enter_clockmenu'},
        {'name': 'original',        'on_enter': 'enter_original'},
        {'name': 'modern',          'on_enter': 'enter_modern', 'on_exit': 'exit_modern'},
        {'name': 'vumeterscreen',   'on_enter': 'enter_vumeterscreen', 'on_exit': 'exit_vumeterscreen'},
        {'name': 'systeminfo',      'on_enter': 'enter_systeminfo'},
        {'name': 'configmenu',      'on_enter': 'enter_configmenu'},

        {'name': 'radiomanager',    'on_enter': 'enter_radiomanager'},
        {'name': 'menu',            'on_enter': 'enter_menu'},
        {'name': 'playlists',       'on_enter': 'enter_playlists'},
        {'name': 'tidal',           'on_enter': 'enter_tidal'},
        {'name': 'qobuz',           'on_enter': 'enter_qobuz'},
        {'name': 'library',         'on_enter': 'enter_library'},
        {'name': 'usblibrary',      'on_enter': 'enter_usb_library'},
        {'name': 'spotify',         'on_enter': 'enter_spotify'},
        {'name': 'webradio',        'on_enter': 'enter_webradio'},
    ]

    def __init__(
        self,
        display_manager,
        clock,
        volumio_listener,           # The Volumio (or Moode) listener
        preference_file_path="../preference.json",
        config=None
    ):
        """
        :param display_manager:   Manages the OLED display
        :param clock:             Clock instance
        :param volumio_listener:  Object that fires state_changed signals from Volumio
        :param preference_file_path: JSON file to store user preferences
        :param config:            Combined config loaded from YAML, etc.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("ModeManager: Initializing...")

        self.display_manager   = display_manager
        self.clock             = clock
        self.volumio_listener  = volumio_listener
        self.config            = config or {}

        self.last_mode_change_time = 0.0
        self.min_mode_switch_interval = 0.5  # e.g. 0.5 seconds

        self.logger.debug("ModeManager: Initialized with last_mode_change_time and min_mode_switch_interval")


        # Preferences path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.preference_file_path = os.path.join(script_dir, preference_file_path)

        preferences = self._load_preferences()
        for key in (
            "display_mode",
            "clock_font_key",
            "show_seconds",
            "show_date",
            "screensaver_enabled",
            "screensaver_type",
            "screensaver_timeout",
            "oled_brightness",
            "cava_enabled",
        ):
            self.config[key] = preferences[key]


        # References to managers or screens (set via a ManagerFactory or manually)
        self.menu_manager           = None
        self.config_menu            = None
        self.playlist_manager       = None
        self.radio_manager          = None
        self.tidal_manager          = None
        self.qobuz_manager          = None
        self.spotify_manager        = None
        self.library_manager        = None
        self.usb_library_manager    = None
        self.original_screen        = None
        self.modern_screen          = None
        self.vumeter_screen          = None
        self.webradio_screen        = None
        self.screensaver            = None
        self.screensaver_menu       = None
        self.display_menu           = None
        self.clock_menu             = None
        self.system_info_screen     = None

        # Screensaver / idle logic
        self.idle_timer       = None
        self.idle_timeout     = self.config.get("screensaver_timeout", 360)

        self.suppress_state_changes = False  # For transitions
        self.is_track_changing      = False
        self.track_change_in_progress = False
        self.current_status         = None
        self.previous_status        = None
        self.pause_stop_timer       = None
        self.pause_stop_delay       = 1.5  # e.g. half-second

        self.logger.debug(f"ModeManager: idle_timeout={self.idle_timeout}, display_mode={self.config.get('display_mode')}")

        # Set up the state machine
        self.machine = Machine(
            model=self,
            states=ModeManager.states,
            initial='clock',  # or 'boot' if you prefer
            send_event=True
        )
        self._define_transitions()  # define transitions from * to any state

        # If volumio_listener is present, connect it
        if self.volumio_listener is not None:
            self.volumio_listener.state_changed.connect(self.process_state_change)
            self.logger.debug("ModeManager: Connected to volumio_listener.state_changed signal.")
        else:
            self.logger.warning("ModeManager: volumio_listener is None, no state_changed signal linked.")

        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    #  Preferences load/save for display mode, brightness, etc.
    # ------------------------------------------------------------------
    def _load_screen_preference(self):
        """Load 'display_mode' from JSON or fallback to 'original'."""
        if os.path.exists(self.preference_file_path):
            try:
                with open(self.preference_file_path, "r") as f:
                    data = json.load(f)
                    mode = data.get("display_mode", "original")
                    self.logger.info(f"Loaded display mode preference: {mode}")
                    return mode
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load preference; defaulting to 'original'. Error: {e}")
        else:
            self.logger.info(f"No preference file at {self.preference_file_path}, using 'original'.")
        return "original"

    def save_preferences(self):
        """Write the updated self.config entries to preference.json."""
        if not self.preference_file_path:
            return
        
        # 1) Load existing JSON if it exists
        if os.path.exists(self.preference_file_path):
            with open(self.preference_file_path, "r") as f:
                try:
                    data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
        else:
            data = {}

        # 2) Copy updated fields from self.config to data
        for key in (
            "display_mode",
            "clock_font_key",
            "show_seconds",
            "show_date",
            "screensaver_enabled",
            "screensaver_type",
            "screensaver_timeout",
            "oled_brightness",
            "cava_enabled"
            
        ):
            # If it’s in our config, put it in data
            if key in self.config:
                data[key] = self.config[key]

        # 3) Write out to JSON
        try:
            with open(self.preference_file_path, "w") as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"ModeManager: Preferences saved to {self.preference_file_path}.")
        except IOError as e:
            self.logger.warning(f"ModeManager: Could not write to {self.preference_file_path}. Error: {e}")


    def set_display_mode(self, mode_name):
        if mode_name in ("original", "modern", "vumeterscreen"):
            self.config["display_mode"] = mode_name
            self.logger.info(f"ModeManager: Display mode set to '{mode_name}'.")
            self.save_preferences()
        else:
            self.logger.warning(f"Unknown display mode '{mode_name}'.")


    def _load_preferences(self):
        default_preferences = {
            "display_mode": "original",
            "clock_font_key": "default",
            "show_seconds": True,
            "show_date": True,
            "screensaver_enabled": False,
            "screensaver_type": "none",
            "screensaver_timeout": 120,
            "oled_brightness": 100,
            "cava_enabled": False,

        }

        if os.path.exists(self.preference_file_path):
            try:
                with open(self.preference_file_path, "r") as f:
                    file_preferences = json.load(f)
                    default_preferences.update(file_preferences)
                    self.logger.info(f"Loaded preferences: {default_preferences}")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load preferences. Using defaults. Error: {e}")
        else:
            self.logger.info(f"No preference file found at {self.preference_file_path}. Using defaults.")

        return default_preferences


    # ------------------------------------------------------------------
    #  Setting references for managers & screens (via ManagerFactory)
    # ------------------------------------------------------------------
    def set_menu_manager(self, menu_manager):
        self.menu_manager = menu_manager

    def set_config_menu(self, config_menu):
        self.config_menu = config_menu

    def set_playlist_manager(self, playlist_manager):
        self.playlist_manager = playlist_manager

    def set_radio_manager(self, radio_manager):
        self.radio_manager = radio_manager

    def set_tidal_manager(self, tidal_manager):
        self.tidal_manager = tidal_manager

    def set_qobuz_manager(self, qobuz_manager):
        self.qobuz_manager = qobuz_manager

    def set_spotify_manager(self, spotify_manager):
        self.spotify_manager = spotify_manager

    def set_library_manager(self, library_manager):
        self.library_manager = library_manager

    def set_usb_library_manager(self, usb_library_manager):
        self.usb_library_manager = usb_library_manager

    def set_original_screen(self, original_screen):
        self.original_screen = original_screen

    def set_modern_screen(self, modern_screen):
        self.modern_screen = modern_screen

    def set_vumeter_screen(self, vumeter_screen):
        self.vumeter_screen = vumeter_screen

    def set_webradio_screen(self, webradio_screen):
        self.webradio_screen = webradio_screen

    def set_clock_menu(self, clock_menu):
        self.clock_menu = clock_menu

    def set_display_menu(self, display_menu):
        self.display_menu = display_menu

    def set_screensaver(self, screensaver):
        self.screensaver = screensaver

    def set_screensaver_menu(self, screensaver_menu):
        self.screensaver_menu = screensaver_menu

    def set_system_info_screen(self, system_info_screen):
        self.system_info_screen = system_info_screen

    # ------------------------------------------------------------------
    #  State-suppression logic (if we want to temporarily block transitions)
    # ------------------------------------------------------------------
    def suppress_state_change(self):
        with self.lock:
            self.suppress_state_changes = True
            self.logger.debug("ModeManager: State changes suppressed.")

    def allow_state_change(self):
        with self.lock:
            self.suppress_state_changes = False
            self.logger.debug("ModeManager: State changes allowed.")

    def is_state_change_suppressed(self):
        return self.suppress_state_changes

    # ------------------------------------------------------------------
    #  IDLE / Screensaver
    # ------------------------------------------------------------------
    def reset_idle_timer(self):
        # Always refresh self.idle_timeout from the latest config
        self.idle_timeout = self.config.get("screensaver_timeout", 360)

        screensaver_enabled = self.config.get("screensaver_enabled", True)
        if not screensaver_enabled:
            self._cancel_idle_timer()
            return

        self._cancel_idle_timer()
        self._start_idle_timer()


    def _start_idle_timer(self):
        if self.idle_timeout <= 0:
            return
        self.idle_timer = threading.Timer(self.idle_timeout, self._idle_timeout_reached)
        self.idle_timer.start()
        self.logger.debug(f"ModeManager: Idle timer started for {self.idle_timeout}s.")

    def _cancel_idle_timer(self):
        if self.idle_timer:
            self.idle_timer.cancel()
            self.idle_timer = None
            self.logger.debug("ModeManager: Idle timer canceled.")

    def _idle_timeout_reached(self):
        with self.lock:
            current_mode = self.get_mode()
            if current_mode == "clock":
                self.logger.debug("ModeManager: Idle timeout => to_screensaver.")
                self.to_screensaver()
            else:
                self.logger.debug(
                    f"ModeManager: Idle in '{current_mode}', not going to screensaver."
                )


    # ------------------------------------------------------------------
    #  Transitions definition
    # ------------------------------------------------------------------
    def _define_transitions(self):
        # Quoode-style
        self.machine.add_transition('to_boot',         source='*', dest='boot')
        self.machine.add_transition('to_clock',        source='*', dest='clock')
        self.machine.add_transition('to_screensaver',  source='*', dest='screensaver')
        self.machine.add_transition('to_screensavermenu', source='*', dest='screensavermenu')
        self.machine.add_transition('to_displaymenu',  source='*', dest='displaymenu')
        self.machine.add_transition('to_clockmenu',    source='*', dest='clockmenu')
        self.machine.add_transition('to_configmenu',    source='*', dest='configmenu')
        self.machine.add_transition('to_original',     source='*', dest='original')
        self.machine.add_transition('to_modern',       source='*', dest='modern')
        self.machine.add_transition('to_vumeterscreen', source='*', dest='vumeterscreen')
        self.machine.add_transition('to_systeminfo',   source='*', dest='systeminfo')

        # Quadify-like
        self.machine.add_transition('to_radiomanager',   source='*', dest='radiomanager')        
        self.machine.add_transition('to_menu',         source='*', dest='menu')
        self.machine.add_transition('to_playlists',    source='*', dest='playlists')
        self.machine.add_transition('to_tidal',        source='*', dest='tidal')
        self.machine.add_transition('to_qobuz',        source='*', dest='qobuz')
        self.machine.add_transition('to_library',      source='*', dest='library')
        self.machine.add_transition('to_usb_library',  source='*', dest='usblibrary')
        self.machine.add_transition('to_spotify',      source='*', dest='spotify')
        self.machine.add_transition('to_webradio',     source='*', dest='webradio')

    # ------------------------------------------------------------------
    #  Expose the transitions
    # ------------------------------------------------------------------
    def trigger(self, event_name, **kwargs):
        self.machine.trigger(event_name, **kwargs)

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def get_mode(self):
        return self.state

    # ------------------------------------------------------------------
    #  Helper: stop_all_screens
    # ------------------------------------------------------------------
    def stop_all_screens(self):
        """
        Stop every known manager/screen if it's active.
        Also stops the clock and screensaver if needed.
        """
        self.logger.debug("ModeManager: stop_all_screens called.")

        # Stop clock if running
        if self.clock:
            self.clock.stop()

        # Stop screensavers
        if self.screensaver:
            self.screensaver.stop_screensaver()
        if self.screensaver_menu and self.screensaver_menu.is_active:
            self.screensaver_menu.stop_mode()

        # Stop other menus
        if self.menu_manager and self.menu_manager.is_active:
            self.menu_manager.stop_mode()
        if self.config_menu and self.config_menu.is_active:
            self.config_menu.stop_mode()
        if self.clock_menu and self.clock_menu.is_active:
            self.clock_menu.stop_mode()
        if self.display_menu and self.display_menu.is_active:
            self.display_menu.stop_mode()

        # Stop managers
        if self.radio_manager and self.radio_manager.is_active:
            self.radio_manager.stop_mode()
        if self.playlist_manager and self.playlist_manager.is_active:
            self.playlist_manager.stop_mode()
        if self.tidal_manager and self.tidal_manager.is_active:
            self.tidal_manager.stop_mode()
        if self.qobuz_manager and self.qobuz_manager.is_active:
            self.qobuz_manager.stop_mode()
        if self.spotify_manager and self.spotify_manager.is_active:
            self.spotify_manager.stop_mode()
        if self.library_manager and self.library_manager.is_active:
            self.library_manager.stop_mode()
        if self.usb_library_manager and self.usb_library_manager.is_active:
            self.usb_library_manager.stop_mode()

        # Stop all possible screens
        if self.original_screen and self.original_screen.is_active:
            self.original_screen.stop_mode()
        if self.modern_screen and self.modern_screen.is_active:
            self.modern_screen.stop_mode()
        if self.vumeter_screen and self.vumeter_screen.is_active:
            self.vumeter_screen.stop_mode()
        if self.webradio_screen and self.webradio_screen.is_active:
            self.webradio_screen.stop_mode()
        if self.system_info_screen and self.system_info_screen.is_active:
            self.system_info_screen.stop_mode()

    # ------------------------------------------------------------------
    #  Helper: set_cava_service_state
    # ------------------------------------------------------------------
    def set_cava_service_state(self, enable: bool, service_name="cava"):
        # 1) Check if the service is active or enabled 
        # to skip repeated calls if no change is needed
        is_active = subprocess.run(
            ["systemctl", "is-active", service_name], capture_output=True, text=True
        ).stdout.strip() == "active"

        is_enabled = subprocess.run(
            ["systemctl", "is-enabled", service_name], capture_output=True, text=True
        ).stdout.strip() == "enabled"

        if enable:
            # Only enable if not already enabled
            if not is_enabled:
                subprocess.run(["sudo", "systemctl", "enable", service_name], check=True)
            # Only start if not already active
            if not is_active:
                subprocess.run(["sudo", "systemctl", "start", service_name], check=True)
        else:
            # Only disable/stop if actually enabled/active
            if is_active:
                subprocess.run(["sudo", "systemctl", "stop", service_name], check=True)
            if is_enabled:
                subprocess.run(["sudo", "systemctl", "disable", service_name], check=True)


    # ------------------------------------------------------------------
    #  State Entry Methods
    # ------------------------------------------------------------------

    def enter_boot(self, event):
        self.logger.info("ModeManager: Entering 'boot' state.")
        # Potentially stop everything if needed
        self.stop_all_screens()
        # Do boot tasks...
        # no screen started here

    def enter_clock(self, event):
        self.logger.info("ModeManager: Entering 'clock' mode.")
        # 1) Stop everything
        self.stop_all_screens()

        # 2) Start clock
        if self.clock:
            self.clock.config = self.config
            self.clock.start()
            self.logger.info("ModeManager: Clock started.")
        else:
            self.logger.warning("ModeManager: No Clock instance.")

        # 3) reset idle timer
        self.reset_idle_timer()

    def enter_modern(self, event):
        self.logger.info("ModeManager: Entering 'modern' playback mode.")
        # 1) Stop all
        self.stop_all_screens()

        # 1) Always stop the VU meter service
        self.set_cava_service_state(False, service_name="cava_vumeter")

        # 2) Check if user wants the standard CAVA
        cava_enabled = self.config.get("cava_enabled", False)
        self.set_cava_service_state(cava_enabled, service_name="cava")

        # 3) Start the modern screen
        if self.modern_screen:
            self.modern_screen.start_mode()
            self.logger.info("ModeManager: Modern screen started.")
        else:
            self.logger.warning("ModeManager: No modern_screen set.")

    def enter_vumeterscreen(self, event):
        self.logger.info("ModeManager: Entering 'vumeterscreen' state.")
        # 1) Stop all
        self.stop_all_screens()

        # 1) Always stop the VU meter service
        self.set_cava_service_state(False, service_name="cava")

        self.set_cava_service_state(True, service_name="cava_vumeter")

        # 3) Now start the VU meter screen
        if self.vumeter_screen:
            self.vumeter_screen.start_mode()
            self.logger.info("ModeManager: VUMeterScreen started.")
        else:
            self.logger.warning("ModeManager: No vumeter_screen set.")

    def enter_radiomanager(self, event):
        self.logger.info("ModeManager: Entering 'radiomanager' state.")
        self.stop_all_screens()
        if self.radio_manager:
            self.radio_manager.start_mode()
            self.logger.info("ModeManager: RadioManager started.")
        else:
            self.logger.warning("ModeManager: No radio_manager set.")
        self.reset_idle_timer()

    def enter_screensaver(self, event):
        self.logger.info("ModeManager: Entering 'screensaver' state.")
        self.stop_all_screens()
        if self.screensaver:
            self.screensaver.start_screensaver()
            self.logger.info("ModeManager: Screensaver started.")
        else:
            self.logger.warning("ModeManager: screensaver is None.")

    def enter_screensavermenu(self, event):
        self.logger.info("ModeManager: Entering 'screensavermenu' state.")
        self.stop_all_screens()
        if self.screensaver_menu:
            self.screensaver_menu.start_mode()
            self.logger.info("ModeManager: Screensaver menu started.")
        else:
            self.logger.warning("ModeManager: No screensaver_menu set.")

    def enter_displaymenu(self, event):
        self.logger.info("ModeManager: Entering 'displaymenu' state.")
        self.stop_all_screens()
        if self.display_menu:
            self.display_menu.start_mode()
            self.logger.info("ModeManager: Display menu started.")
        else:
            self.logger.warning("ModeManager: No display_menu set.")
        self.reset_idle_timer()

    def enter_clockmenu(self, event):
        self.logger.info("ModeManager: Entering 'clockmenu' state.")
        self.stop_all_screens()
        if self.clock_menu:
            self.clock_menu.start_mode()
            self.logger.info("ModeManager: Clock menu started.")
        else:
            self.logger.warning("ModeManager: No clock_menu set.")
        self.reset_idle_timer()

    def enter_original(self, event):
        self.logger.info("ModeManager: Entering 'original' playback mode.")
        self.stop_all_screens()
        if self.original_screen:
            self.original_screen.start_mode()
            self.logger.info("ModeManager: Original screen started.")
        else:
            self.logger.warning("ModeManager: No original_screen set.")

    def enter_systeminfo(self, event):
        self.logger.info("ModeManager: Entering 'systeminfo' mode.")
        self.stop_all_screens()
        if self.system_info_screen:
            self.system_info_screen.start_mode()
            self.logger.info("ModeManager: SystemInfoScreen started.")
        else:
            self.logger.warning("ModeManager: No system_info_screen set.")
        self.reset_idle_timer()

    def enter_menu(self, event):
        self.logger.info("ModeManager: Entering 'menu' state.")
        self.stop_all_screens()

        if self.menu_manager:
            self.menu_manager.start_mode()
            self.logger.info("ModeManager: MenuManager started.")
        else:
            self.logger.warning("ModeManager: No menu_manager set.")
        self.reset_idle_timer()

    def enter_playlists(self, event):
        self.logger.info("ModeManager: Entering 'playlists' state.")
        self.stop_all_screens()
        if self.playlist_manager:
            self.playlist_manager.start_mode()
            self.logger.info("ModeManager: PlaylistManager started.")
        else:
            self.logger.warning("ModeManager: No playlist_manager set.")
        self.reset_idle_timer()

    def enter_tidal(self, event):
        self.logger.info("ModeManager: Entering 'tidal' state.")
        self.stop_all_screens()
        if self.tidal_manager:
            self.tidal_manager.start_mode()
            self.logger.info("ModeManager: TidalManager started.")
        else:
            self.logger.warning("ModeManager: No tidal_manager set.")
        self.reset_idle_timer()

    def enter_qobuz(self, event):
        self.logger.info("ModeManager: Entering 'qobuz' state.")
        self.stop_all_screens()
        if self.qobuz_manager:
            self.qobuz_manager.start_mode()
            self.logger.info("ModeManager: QobuzManager started.")
        else:
            self.logger.warning("ModeManager: No qobuz_manager set.")
        self.reset_idle_timer()

    def enter_library(self, event):
        self.logger.info("ModeManager: Entering 'library' state.")
        self.stop_all_screens()
        if self.library_manager:
            start_uri = event.kwargs.get('start_uri')
            self.library_manager.start_mode(start_uri=start_uri)
            self.logger.info("ModeManager: LibraryManager started.")
        else:
            self.logger.warning("ModeManager: No library_manager set.")
        self.reset_idle_timer()

    def enter_usb_library(self, event):
        self.logger.info("ModeManager: Entering 'usblibrary' state.")
        self.stop_all_screens()
        if self.usb_library_manager:
            start_uri = event.kwargs.get('start_uri')
            self.usb_library_manager.start_mode(start_uri=start_uri)
            self.logger.info("ModeManager: USBLibraryManager started.")
        else:
            self.logger.warning("ModeManager: No usb_library_manager set.")
        self.reset_idle_timer()

    def enter_spotify(self, event):
        self.logger.info("ModeManager: Entering 'spotify' state.")
        self.stop_all_screens()
        if self.spotify_manager:
            self.spotify_manager.start_mode()
            self.logger.info("ModeManager: SpotifyManager started.")
        else:
            self.logger.warning("ModeManager: No spotify_manager set.")

    def enter_webradio(self, event):
        self.logger.info("ModeManager: Entering 'webradio' state.")
        self.stop_all_screens()
        if self.webradio_screen:
            self.webradio_screen.start_mode()
            self.logger.info("ModeManager: WebRadioScreen started.")
        else:
            self.logger.warning("ModeManager: No webradio_screen set.")


    def enter_configmenu(self, event):
        self.logger.info("ModeManager: Entering 'configmenu'.")
        
        self.stop_all_screens()

        if self.config_menu:
            self.config_menu.start_mode()
            self.logger.info("ModeManager: Config menu started.")
        else:
            self.logger.warning("ModeManager: No config_menu set.")


    def exit_screensaver(self):
        self.logger.info("ModeManager: Exiting screensaver mode.")
        if self.screensaver:
            self.screensaver.stop_screensaver()
        self.to_clock()

    def exit_modern(self, event):
        self.logger.info("ModeManager: Exiting 'modern' => stopping cava.service")
        self.display_manager.clear_screen()

    def exit_vumeterscreen(self, event):
        self.logger.info("ModeManager: Exiting 'vumeterscreen' => stopping cava_vumeter.service")
        self.display_manager.clear_screen()

    # ------------------------------------------------------------------
    #  Playback / Volumio state handling
    # ------------------------------------------------------------------
    def process_state_change(self, sender, state, **kwargs):
        with self.lock:
            if self.suppress_state_changes:
                self.logger.debug("ModeManager: State changes suppressed.")
                return

            self.logger.debug(f"ModeManager: process_state_change => {state}")
            status  = state.get('status', '').lower()
            service = state.get('service', '').lower()

            self.previous_status = self.current_status
            self.current_status  = status

            # Identify track change from play->stop or stop->play
            if self.previous_status == "play" and self.current_status == "stop":
                self._handle_track_change()

            # Now handle logic for 'play', 'pause', 'stop' in one place
            self._handle_playback_states(status, service)

            self.logger.debug("ModeManager: Completed process_state_change.")


    def _handle_track_change(self):
        """
        Possibly the track ended or user pressed stop. 
        Start a short timer to see if user restarts or if we stay stopped.
        """
        self.is_track_changing = True
        self.track_change_in_progress = True

        if not self.pause_stop_timer:
            self.pause_stop_timer = threading.Timer(
                self.pause_stop_delay,
                self.switch_to_clock_if_still_stopped_or_paused
            )
            self.pause_stop_timer.start()
            self.logger.debug("ModeManager: Started stop verification timer.")



    def _handle_playback_states(self, status, service):
        now = time.time()
        desired_mode = self.config.get("display_mode", "original")

        # 1) If too soon since last mode switch, skip
        if (now - self.last_mode_change_time) < self.min_mode_switch_interval:
            self.logger.debug("ModeManager: Ignoring rapid consecutive playback-state => no mode switch.")
            return

        if status == "play":
            # 2) Check if we're already in the correct mode
            current_mode = self.get_mode()  # e.g. "vumeterscreen", "modern", etc.

            if desired_mode == "vumeterscreen":
                if current_mode == "vumeterscreen":
                    self.logger.debug("ModeManager: Already in vumeterscreen, skipping transition.")
                else:
                    self.to_vumeterscreen()
                    self.last_mode_change_time = now

            elif desired_mode == "modern":
                if current_mode == "modern":
                    self.logger.debug("ModeManager: Already in modern, skipping transition.")
                else:
                    self.to_modern()
                    self.last_mode_change_time = now

            else:
                # default to original
                if current_mode == "original":
                    self.logger.debug("ModeManager: Already in original, skipping transition.")
                else:
                    self.to_original()
                    self.last_mode_change_time = now

            self.reset_idle_timer()

        elif status == "pause":
            # (whatever logic you already have)
            self._start_pause_timer()



    def _start_pause_timer(self):
        """
        If we just paused or stopped, revert to clock
        after self.pause_stop_delay unless user resumes.
        """
        if not self.pause_stop_timer:
            self.pause_stop_timer = threading.Timer(
                self.pause_stop_delay,
                self.switch_to_clock_if_still_stopped_or_paused
            )
            self.pause_stop_timer.start()
            self.logger.debug("ModeManager: Started pause/stop timer.")
        else:
            self.logger.debug("ModeManager: pause/stop timer already running.")



    def _cancel_pause_timer(self):
        """Stop the pause/stop timer if it’s active."""
        if self.pause_stop_timer:
            self.pause_stop_timer.cancel()
            self.pause_stop_timer = None
            self.logger.debug("ModeManager: Canceled pause/stop timer.")


    def switch_to_clock_if_still_stopped_or_paused(self):
        with self.lock:
            if self.current_status in ["pause", "stop"]:
                self.to_clock()
                self.logger.debug("ModeManager: Reverted to clock after pause/stop timer.")
            else:
                self.logger.debug("ModeManager: Playback resumed or changed; staying in current mode.")
            self.pause_stop_timer = None




