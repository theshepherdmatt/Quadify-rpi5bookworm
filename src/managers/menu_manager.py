import logging
import threading
import time
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
import glob

from network.service_listener import get_available_services

class MenuManager:
    def __init__(self, display_manager, volumio_listener, mode_manager, window_size=5, menu_type="icon_row"):
        self.display_manager = display_manager
        self.volumio_listener = volumio_listener
        self.mode_manager = mode_manager

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.info("MenuManager initialized.")

        self.menu_stack = []
        self.current_menu_items = []
        self.current_selection_index = 0
        self.is_active = False
        self.window_size = window_size
        self.window_start_index = 0
        self.menu_type = menu_type
        self.font_key = 'menu_font'
        self.bold_font_key = 'menu_font_bold'
        self.lock = threading.Lock()

        self.label_map = {
            "Library": "MUSIC_LIBRARY",
            "Artists": "ARTISTS",
            "Albums": "ALBUMS",
            "Genres": "GENRES",
            "Radio": "WEB_RADIO",
            "RADIO-P": "Radio-P",
            "RADIO_PARADISE": "Radio-P",
            "Tidal": "TIDAL",
            "Internal": "INTERNAL",
            "Config": "CONFIG",
            "NAS": "NAS",
            "USB": "USB",
            "Playlists": "PLAYLISTS",
            "Spotify": "SPOTIFY",
            "Qobuz": "QOBUZ",
            "Mother-E": "MOTHEREARTH",
            "Mother Earth": "MOTHEREARTH",
        }

        # Static fallback icons mapped by label
        self.static_icons = {
            "Stream": self.display_manager.icons.get("stream"),
            "Library": self.display_manager.icons.get("library"),
            "Radio": self.display_manager.icons.get("webradio"),
            "Radio-P": self.display_manager.icons.get("radio_paradise"),
            "MOTHER-E": self.display_manager.icons.get("motherearthradio"),
            "Playlists": self.display_manager.icons.get("playlists"),
            "Tidal": self.display_manager.icons.get("tidal"),
            "Qobuz": self.display_manager.icons.get("qobuz"),
            "Spotify": self.display_manager.icons.get("spop"),
            "INTERNAL": self.display_manager.icons.get("mpd"),
            "NAS": self.display_manager.icons.get("nas"),
            "USB": self.display_manager.icons.get("usb"),
            "Config": self.display_manager.icons.get("config"),
            "Original": self.display_manager.icons.get("display"),
            "Modern": self.display_manager.icons.get("display"),
        }

        # Cache for fetched icons keyed by menu label
        self.icon_cache = {}

        # Load local PNG icons into icon_cache
        self.local_icon_dir = '/home/volumio/Quadify/src/assets/pngs'
        for icon_path in glob.glob(os.path.join(self.local_icon_dir, '*.png')):
            try:
                key = os.path.splitext(os.path.basename(icon_path))[0].upper()
                img = Image.open(icon_path).convert("RGBA")
                self.icon_cache[key] = img
                self.logger.info(f"Loaded local icon: {key} from {icon_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load local icon {icon_path}: {e}")

            if "LIBRARY" not in self.icon_cache and "MUSIC_LIBRARY" in self.icon_cache:
                self.icon_cache["LIBRARY"] = self.icon_cache["MUSIC_LIBRARY"]
                self.logger.info("MenuManager: Mapped LIBRARY icon to MUSIC_LIBRARY.png as fallback.")

            if "RADIO" not in self.icon_cache and "WEB_RADIO" in self.icon_cache:
                self.icon_cache["RADIO"] = self.icon_cache["WEB_RADIO"]
                self.logger.info("MenuManager: Mapped RADIO icon to WEB_RADIO.png as fallback.")

            if "RADIO-P" not in self.icon_cache and "RADIO_PARADISE" in self.icon_cache:
                self.icon_cache["RADIO-P"] = self.icon_cache["RADIO_PARADISE"]
                self.logger.info("MenuManager: Mapped RADIO icon to RADIO_PARADISE.png as fallback.")

        if hasattr(self.mode_manager, "add_on_mode_change_callback"):
            self.mode_manager.add_on_mode_change_callback(self.handle_mode_change)

    def handle_mode_change(self, current_mode):
        self.logger.info(f"MenuManager handling mode change to: {current_mode}")
        if current_mode == "menu":
            self.start_mode()
        elif self.is_active:
            self.stop_mode()

    def start_mode(self, skip_initial_draw=False):
        self.is_active = True
        self.refresh_main_menu()
        if not skip_initial_draw:
            threading.Thread(target=self.display_menu, daemon=True).start()

    def stop_mode(self):
        if not self.is_active:
            return
        self.is_active = False
        with self.lock:
            self.display_manager.clear_screen()
        self.logger.info("MenuManager: Stopped menu mode and cleared display.")

    # ----------- MENU BUILDING -----------

    def refresh_main_menu(self):
        """Fetches available services and updates the menu."""
        services = []
        VOLUMIO_HOST = 'http://localhost:3000'

        try:
            raw_services = get_available_services()
            for svc in raw_services:
                label = self._map_plugin_to_label(svc['name'], svc['plugin'])
                if label not in services and label != "Library" and label not in ("INTERNAL", "NAS"):
                    services.append(label)
        except Exception as e:
            self.logger.error(f"Error getting available services: {e}")
            services = ["Radio", "Playlists"]  # fallback

        if "Config" not in services:
            services.append("Config")

        self.current_menu_items = services
        self.current_selection_index = 0
        self.window_start_index = 0


    def _map_plugin_to_label(self, name, plugin):
        plugin = plugin.lower()
        # Make mapping robust: replace spaces with hyphens
        normalised_name = name.lower().replace(' ', '-')
        if plugin == "mpd":
            mapping = {
                "music-library": "LIBRARY",
                "artists": "ARTISTS",
                "albums": "ALBUMS",
                "internal": "INTERNAL",
                "nas": "NAS",
                "usb": "USB",
            }
            return mapping.get(normalised_name, name.upper().replace(' ', '_'))
        mapping = {
            "tidal": "TIDAL",
            "qobuz": "QOBUZ",
            "spop": "SPOTIFY",
            "webradio": "RADIO",
            "radio_paradise": "RADIO-P",
            "motherearthradio": "MOTHER-E",
            "playlists": "PLAYLISTS",
        }
        return mapping.get(plugin, name.upper().replace(' ', '_'))



    # ----------- MENU RENDERING -----------

    def draw_menu(self, offset_x=0):
        with self.lock:
            visible_items = self.get_visible_window(self.current_menu_items, self.window_size)
            icon_size = 50
            spacing = -5
            total_width = self.display_manager.oled.width
            total_height = self.display_manager.oled.height
            total_icons_width = len(visible_items) * icon_size + (len(visible_items) - 1) * spacing
            x_offset = (total_width - total_icons_width) // 2 + offset_x
            y_position = (total_height - icon_size) // 2 - 10

            base_image = Image.new("RGB", self.display_manager.oled.size, "black")
            draw_obj = ImageDraw.Draw(base_image)

            for i, item in enumerate(visible_items):
                actual_index = self.window_start_index + i
                icon = self.icon_cache.get(item.upper())
                if not icon:
                    self.logger.warning(f"No icon cached for {item}, skipping.")
                    continue

                if icon.mode == "RGBA":
                    background = Image.new("RGB", icon.size, (0, 0, 0))
                    background.paste(icon, mask=icon.split()[3])
                    icon = background

                icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
                x = x_offset + i * (icon_size + spacing)
                y_adjustment = -5 if actual_index == self.current_selection_index else 0
                base_image.paste(icon, (x, y_position + y_adjustment))

                label = self.label_map.get(item, item.title().replace('_', ' '))
                font = self.display_manager.fonts.get(
                    self.bold_font_key if actual_index == self.current_selection_index else self.font_key,
                    ImageFont.load_default(),
                )
                text_color = "white" if actual_index == self.current_selection_index else "black"
                tw, th = draw_obj.textsize(label, font=font)
                text_x = x + (icon_size - tw) // 2
                text_y = y_position + icon_size + 2
                draw_obj.text((text_x, text_y), label, font=font, fill=text_color)

            base_image = base_image.convert(self.display_manager.oled.mode)
            self.display_manager.oled.display(base_image)

    def slide_in_right(self, duration=0.5, fps=30):
        w = self.display_manager.oled.width
        frames = int(duration * fps)
        for step in range(frames + 1):
            offset = int(w - (w * step) / frames)
            self.draw_menu(offset_x=offset)
            time.sleep(duration / frames)
        self.display_menu()

    def display_menu(self):
        self.draw_menu(offset_x=0)

    # ----------- MENU NAVIGATION -----------

    def config_menu(self):
        self.logger.info("MenuManager: Entering Config menu.")
        self.current_selection_index = 0
        self.window_start_index = 0
        self.display_menu()

    def get_visible_window(self, items, window_size):
        half = window_size // 2
        self.window_start_index = self.current_selection_index - half
        if self.window_start_index < 0:
            self.window_start_index = 0
        elif self.window_start_index + window_size > len(items):
            self.window_start_index = max(len(items) - window_size, 0)
        return items[self.window_start_index : self.window_start_index + window_size]

    def scroll_selection(self, direction):
        if not self.is_active or not self.current_menu_items:
            return

        next_index = self.current_selection_index
        while True:
            next_index += direction
            if not (0 <= next_index < len(self.current_menu_items)):
                break
            # Skip dummy slots
            if self.current_menu_items[next_index] != "":
                self.current_selection_index = next_index
                break
        self.display_menu()


    def select_item(self):
        if not self.is_active or not self.current_menu_items:
            return
        selected = self.current_menu_items[self.current_selection_index]
        self.logger.info(f"MenuManager: Selected menu item: {selected}")
        threading.Thread(target=self._handle_selection, args=(selected,), daemon=True).start()

    def show_music_library_sources_menu(self):
        all_sources = ["INTERNAL", "USB", "NAS"]
        try:
            services = get_available_services()
            available = [svc['name'].upper() for svc in services]
        except Exception as e:
            self.logger.error(f"Failed to get available services: {e}")
            available = []
        sources = [src for src in all_sources if src in available]
        sources.append("BACK")
        self.current_menu_items = sources
        self.current_selection_index = 0
        self.window_start_index = 0
        self.display_menu()

    def _handle_selection(self, selected_item):
        time.sleep(0.2)
        key = str(selected_item).strip().upper()

        # Handle Music Library source submenu logic
        if self.current_menu_items and set(self.current_menu_items).issubset({"INTERNAL", "USB", "NAS", "BACK"}):
            self._handle_music_library_source_selection(key)
            return

        # Main menu action handling
        if key in ["MUSIC_LIBRARY", "LIBRARY"]:
            self.show_music_library_sources_menu()
            self.logger.info("Showing Music Library source picker submenu.")
        elif key == "RADIO":
            self.mode_manager.to_radiomanager()
        elif key == "PLAYLISTS":
            self.mode_manager.to_playlists()
        elif key == "CONFIG":
            self.mode_manager.to_configmenu()
        elif key == "TIDAL":
            self.mode_manager.to_tidal()
        elif key == "QOBUZ":
            self.mode_manager.to_qobuz()
        elif key in ["RADIO_PARADISE", "RADIO-P"]:
            self.mode_manager.to_radioparadise()
        elif key in ["MOTHEREARTH", "MOTHER-E"]:
            self.mode_manager.to_motherearthradio()
        elif key == "SPOTIFY":
            self.mode_manager.to_spotify()
        elif key == "ALBUMS":
            self.mode_manager.to_albums()
        elif key == "ARTISTS":
            self.mode_manager.to_artists()
        elif key == "GENRES":
            self.mode_manager.to_genres()
        else:
            self.logger.warning(f"MenuManager: Unhandled menu selection key '{key}'")


    def _handle_music_library_source_selection(self, selected_source):
        if not selected_source:
            return  # Ignore dummy slots
        key = str(selected_source).strip().upper()
        if key == "INTERNAL":
            self.mode_manager.to_internal()
        elif key == "USB":
            self.mode_manager.to_usb_library()
        elif key == "NAS":
            self.mode_manager.to_library(start_uri="music-library/NAS")  # your NAS browser/LibraryManager
        elif key == "BACK":
            self.mode_manager.to_menu()
        else:
            self.logger.warning(f"MenuManager: Unknown library source '{key}'")

    def render_to_image(self, offset_x=0):
        icon_size = 30
        spacing = 15
        total_width = self.display_manager.oled.width
        total_height = self.display_manager.oled.height

        visible_items = self.get_visible_window(self.current_menu_items, self.window_size)
        total_icons_width = len(visible_items) * icon_size + (len(visible_items) - 1) * spacing
        x_offset = (total_width - total_icons_width) // 2 + offset_x
        y_position = (total_height - icon_size) // 2 - 10

        base_image = Image.new("RGBA", self.display_manager.oled.size, (0, 0, 0, 0))
        draw_obj = ImageDraw.Draw(base_image)

        for i, item in enumerate(visible_items):
            actual_index = self.window_start_index + i
            if item == "":
                # Draw a blank slot or faded icon if you want, or skip entirely:
                # Example: faded/greyed-out placeholder
                faded_colour = (40, 40, 40, 120)
                box_x = x_offset + i * (icon_size + spacing)
                box_y = y_position
                draw_obj.rectangle([box_x, box_y, box_x + icon_size, box_y + icon_size], fill=faded_colour, outline=None)
                continue  # Skip drawing icon/label
            icon = self.icon_cache.get(item) or self.static_icons.get(item, self.display_manager.default_icon)
            if icon.mode == "RGBA":
                bg = Image.new("RGB", icon.size, (0, 0, 0))
                bg.paste(icon, mask=icon.split()[3])
                icon = bg
            icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
            x = x_offset + i * (icon_size + spacing)
            y_adj = -5 if actual_index == self.current_selection_index else 0
            base_image.paste(icon, (x, y_position + y_adj))
            label = item
            font = self.display_manager.fonts.get(
                self.bold_font_key if actual_index == self.current_selection_index else self.font_key,
                ImageFont.load_default(),
            )
            text_color = "white" if actual_index == self.current_selection_index else "black"
            tw, th = draw_obj.textsize(label, font=font)
            text_x = x + (icon_size - tw) // 2
            text_y = y_position + icon_size + 2
            draw_obj.text((text_x, text_y), label, font=font, fill=text_color)

        return base_image
