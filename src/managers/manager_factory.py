# src/managers/manager_factory.py

import logging


class ManagerFactory:
    """
    Responsible for creating and configuring all screens/managers needed by Quadify (Volumio edition).
    """

    def __init__(self, display_manager, volumio_listener, mode_manager, config):
        """
        :param display_manager:   DisplayManager instance
        :param volumio_listener:  VolumioListener instance
        :param mode_manager:      ModeManager instance (to be set with created managers/screens)
        :param config:            Merged config dict from YAML, etc.
        """
        self.display_manager   = display_manager
        self.volumio_listener  = volumio_listener
        self.mode_manager      = mode_manager
        self.config            = config

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.info("ManagerFactory initialized.")

    def setup_mode_manager(self):
        """
        Create and configure all managers/screens, then assign them to ModeManager (or other places).
        """
        # ----- Create each object -----

        # Quadify "menu" managers
        menu_manager         = self.create_menu_manager()
        tidal_manager        = self.create_tidal_manager()
        qobuz_manager        = self.create_qobuz_manager()
        playlist_manager     = self.create_playlist_manager()
        motherearth_manager  = self.create_motherearth_manager()
        radioparadise_manager = self.create_radioparadise_manager()
        radio_manager        = self.create_radio_manager()
        spotify_manager      = self.create_spotify_manager()
        library_manager      = self.create_library_manager()
        usb_library_manager  = self.create_usb_library_manager()

        # Quoode/Quadify common screens
        webradio_screen      = self.create_webradio_screen()
        modern_screen        = self.create_modern_screen()
        minimal_screen        = self.create_minimal_screen()
        original_screen      = self.create_original_screen()
        airplay_screen      = self.create_airplay_screen()

        # Additional items referenced by new ModeManager states
        config_menu          = self.create_config_menu()
        clock_menu           = self.create_clock_menu()
        remote_menu           = self.create_remote_menu()
        display_menu         = self.create_display_menu()
        screensaver_menu     = self.create_screensaver_menu()
        screensaver          = self.create_screensaver()
        system_info_screen   = self.create_system_info_screen()
        system_update_menu   = self.create_system_update_menu()

        # ----- Assign them to ModeManager via the set_* methods -----
        self.mode_manager.set_menu_manager(menu_manager)
        self.mode_manager.set_config_menu(config_menu)
        self.mode_manager.set_tidal_manager(tidal_manager)
        self.mode_manager.set_qobuz_manager(qobuz_manager)
        self.mode_manager.set_playlist_manager(playlist_manager)
        self.mode_manager.set_radio_manager(radio_manager)
        self.mode_manager.set_motherearth_manager(motherearth_manager)
        self.mode_manager.set_radioparadise_manager(radioparadise_manager)
        self.mode_manager.set_spotify_manager(spotify_manager)
        self.mode_manager.set_library_manager(library_manager)
        self.mode_manager.set_usb_library_manager(usb_library_manager)

        self.mode_manager.set_webradio_screen(webradio_screen)
        self.mode_manager.set_modern_screen(modern_screen)
        self.mode_manager.set_minimal_screen(minimal_screen)
        self.mode_manager.set_original_screen(original_screen)
        self.mode_manager.set_airplay_screen(airplay_screen)

        self.mode_manager.set_clock_menu(clock_menu)
        self.mode_manager.set_remote_menu(remote_menu)
        self.mode_manager.set_display_menu(display_menu)
        self.mode_manager.set_screensaver_menu(screensaver_menu)
        self.mode_manager.set_screensaver(screensaver)
        self.mode_manager.set_system_info_screen(system_info_screen)
        self.mode_manager.set_system_update_menu(system_update_menu)

        self.logger.info("ManagerFactory: ModeManager fully configured with managers & screens.")

    # ----------------------------------------------------------------
    #  Create Methods for each manager/screen
    # ----------------------------------------------------------------

    def create_menu_manager(self):
        from managers.menu_manager import MenuManager
        return MenuManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )
    
    def create_config_menu(self):
        from .menus.config_menu import ConfigMenu
        return ConfigMenu(
            display_manager   = self.display_manager,
            mode_manager      = self.mode_manager
        )

    def create_remote_menu(self):
        from .menus.remote_menu import RemoteMenu
        return RemoteMenu(
            display_manager   = self.display_manager,
            mode_manager      = self.mode_manager
        )

    def create_tidal_manager(self):
        from .menus.tidal_manager import TidalManager
        return TidalManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_qobuz_manager(self):
        from .menus.qobuz_manager import QobuzManager
        return QobuzManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_playlist_manager(self):
        from .menus.playlist_manager import PlaylistManager
        return PlaylistManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_radio_manager(self):
        from .menus.radio_manager import RadioManager
        return RadioManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )
    
    def create_motherearth_manager(self):
        from .menus.motherearth_manager import MotherEarthManager
        return MotherEarthManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_radioparadise_manager(self):
        from .menus.radioparadise_manager import RadioParadiseManager
        return RadioParadiseManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )


    def create_spotify_manager(self):
        from .menus.spotify_manager import SpotifyManager
        return SpotifyManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_library_manager(self):
        from .menus.library_manager import LibraryManager
        return LibraryManager(
            display_manager   = self.display_manager,
            volumio_config    = self.config.get('volumio', {}),
            mode_manager      = self.mode_manager
        )

    def create_usb_library_manager(self):
        from .menus.usb_library_manager import USBLibraryManager
        return USBLibraryManager(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_webradio_screen(self):
        from display.screens.webradio_screen import WebRadioScreen
        return WebRadioScreen(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )
    
    def create_airplay_screen(self):
        from display.screens.airplay_screen import AirPlayScreen
        return AirPlayScreen(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_modern_screen(self):
        from display.screens.modern_screen import ModernScreen
        return ModernScreen(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )
    
    def create_minimal_screen(self):
        from display.screens.minimal_screen import MinimalScreen
        return MinimalScreen(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    def create_original_screen(self):
        from display.screens.original_screen import OriginalScreen
        return OriginalScreen(
            display_manager   = self.display_manager,
            volumio_listener  = self.volumio_listener,
            mode_manager      = self.mode_manager
        )

    # ----------------------------------------------------------------
    #  New create methods for Quoode/Quadify synergy
    # ----------------------------------------------------------------

    def create_clock_menu(self):
        from .menus.clock_menu import ClockMenu
        return ClockMenu(
            display_manager   = self.display_manager,
            mode_manager      = self.mode_manager
        )

    def create_display_menu(self):
        from .menus.display_menu import DisplayMenu
        return DisplayMenu(
            display_manager   = self.display_manager,
            mode_manager      = self.mode_manager
        )

    def create_screensaver_menu(self):
        from .menus.screensaver_menu import ScreensaverMenu
        return ScreensaverMenu(
            display_manager   = self.display_manager,
            mode_manager      = self.mode_manager
        )

    def create_screensaver(self):
        """
        Creates a Screensaver instance based on self.config["screensaver_type"].
        """
        screensaver_type = self.config.get("screensaver_type", "generic").lower()

        if screensaver_type == "snake":
            from display.screensavers.snake_screensaver import SnakeScreensaver
            self.logger.info("ManagerFactory: Using SnakeScreensaver.")
            return SnakeScreensaver(
                display_manager=self.display_manager,
                update_interval=0.04
            )
        
        elif screensaver_type in ("geo"):
            from display.screensavers.geo_screensaver import GeoScreensaver
            self.logger.info("ManagerFactory: Using GeoScreensaver.")
            return GeoScreensaver(
                display_manager=self.display_manager,
                update_interval=0.06
            )


        elif screensaver_type in ("quadify", "bouncing_text"):
            from display.screensavers.bouncing_text_screensaver import BouncingTextScreensaver
            self.logger.info("ManagerFactory: Using BouncingTextScreensaver.")
            return BouncingTextScreensaver(
                display_manager=self.display_manager,
                text="Quadify",
                update_interval=0.06
            )
        else:
            # Fallback to the generic blank one
            from display.screensavers.screensaver import Screensaver
            self.logger.info(f"ManagerFactory: Using generic Screensaver (type={screensaver_type}).")
            return Screensaver(
                display_manager=self.display_manager,
                update_interval=0.05
            )


    def create_system_info_screen(self):
        from display.screens.system_info_screen import SystemInfoScreen
        return SystemInfoScreen(
            display_manager   = self.display_manager,
            volumio_listener    = self.volumio_listener,  # or rename param if needed
            mode_manager      = self.mode_manager
        )

    def create_system_update_menu(self):
        from .menus.system_update_menu import SystemUpdateMenu
        return SystemUpdateMenu(
            display_manager = self.display_manager,
            mode_manager    = self.mode_manager
        )
