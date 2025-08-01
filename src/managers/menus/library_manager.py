import os
import json
import logging
import requests
import threading
from threading import Event, Thread
from requests.adapters import HTTPAdapter
from urllib.parse import quote
from urllib3.util.retry import Retry
from PIL import ImageFont

from managers.base_manager import BaseManager  # Adjust as per your project structure

class LibraryManager(BaseManager):
    def __init__(self, display_manager, volumio_config, mode_manager, service_type, root_uri, window_size=3, y_offset=0, line_spacing=16):
        super().__init__(display_manager, volumio_config, mode_manager)

        # API setup
        self.volumio_host = volumio_config.get('host', 'localhost')
        self.volumio_port = volumio_config.get('port', 3000)
        self.base_url = f"http://{self.volumio_host}:{self.volumio_port}"

        # Session with retries
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        self.selection_lock = threading.Lock()
        self.is_active = False

        self.window_size = window_size
        self.y_offset = y_offset
        self.line_spacing = line_spacing
        self.font_key = 'menu_font'

        self.service_type = service_type  # e.g., 'library', 'tidal', 'qobuz'
        self.root_uri = root_uri          # e.g., 'music-library/NAS/Music', 'tidal', 'qobuz://'

        self.menu_stack = []
        self.current_menu_items = []
        self.current_selection_index = 0
        self.window_start_index = 0

        self.current_path = self.root_uri

        self.config = self.display_manager.config
        display_config = self.config.get('display', {})
        self.icon_dir = display_config.get('icon_dir', '/home/volumio/Quadify/src/assets/images')

        if hasattr(self.mode_manager, "add_on_mode_change_callback"):
            self.mode_manager.add_on_mode_change_callback(self.handle_mode_change)

    def handle_mode_change(self, current_mode):
        self.logger.info(f"[{self.service_type}] Mode change: {current_mode}")
        if current_mode == self.service_type:
            self.start_mode()
        elif self.is_active:
            self.stop_mode()

    def start_mode(self, start_uri=None):
        if self.is_active:
            self.logger.debug(f"[{self.service_type}] Already active, ignoring start_mode()")
            return
        self.is_active = True
        self.current_selection_index = 0
        self.window_start_index = 0
        self.menu_stack.clear()
        self.current_path = start_uri or self.root_uri
        self.logger.info(f"[{self.service_type}] Starting mode with URI: {self.current_path}")
        self.display_loading_screen()
        self.fetch_navigation(self.current_path)
        self.timeout_timer = threading.Timer(3.0, self.library_timeout)
        self.timeout_timer.start()

    def library_timeout(self):
        if not self.current_menu_items:
            self.logger.warning(f"[{self.service_type}] Timeout: No items loaded for path '{self.current_path}'.")
            self.display_message("Your library is not loading...", "Have you enabled it via Volumio?")
            threading.Timer(5.0, self.mode_manager.to_menu).start()

    def stop_mode(self):
        self.logger.info(f"[{self.service_type}] Stopping mode and clearing display.")
        self.is_active = False
        self.display_manager.clear_screen()

    def fetch_navigation(self, uri):
        self.logger.info(f"[{self.service_type}] Fetching navigation for URI: {uri}")
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/browse?uri={quote(uri)}")
            if resp.status_code != 200:
                self.logger.error(f"[{self.service_type}] Fetch Error: Status {resp.status_code} for URI '{uri}'")
                self.display_message("Fetch Error", f"Failed: {resp.status_code}")
                return
            nav = resp.json().get("navigation", {})
            items = nav.get("lists", [{}])[0].get("items", [])
            if not items:
                self.logger.warning(f"[{self.service_type}] No items in folder '{uri}'.")
                self.display_message("No Items", "This folder is empty.")
                return
            self.logger.debug(f"[{self.service_type}] {len(items)} items loaded from '{uri}'.")
            self.current_menu_items = [
                {
                    "title": item.get("title", "Untitled"),
                    "uri": item.get("uri", ""),
                    "type": item.get("type", "").lower(),
                    "service": item.get("service", "").lower(),
                    "albumart": item.get("albumart", None)
                }
                for item in items
            ]
            self.current_menu_items.append({"title": "Back", "uri": None, "type": "back"})
            if self.is_active:
                self.display_menu()
        except Exception as e:
            self.logger.error(f"[{self.service_type}] Exception in fetch_navigation: {e}")
            self.display_message("Error", str(e))

    def play_streaming_song(self, item):
        """
        Play a song/track for streaming services like Tidal or Qobuz, etc.
        """
        service = item.get("service", self.service_type)
        uri = item.get("uri")
        self.logger.info(f"[{self.service_type}] Playing streaming item via replaceAndPlay: {item}")
        if not uri:
            self.display_message("Playback Error", "No URI for this item.")
            return
        try:
            # Prefer SocketIO if available (for Volumio streaming services)
            if hasattr(self.display_manager, "volumio_listener") and hasattr(self.display_manager.volumio_listener, "socketIO"):
                self.display_manager.volumio_listener.socketIO.emit('replaceAndPlay', {
                    "item": {
                        "service": service,
                        "uri": uri
                    }
                })
            else:
                # fallback to HTTP API
                url = f"{self.base_url}/api/v1/replaceAndPlay"
                data = {"name": item.get("title", ""), "service": service, "uri": uri}
                self.session.post(url, json=data)
            self.display_message("Playback Started", f"Playing: {item.get('title', '')}")
        except Exception as e:
            self.display_message("Playback Error", str(e))

    def navigate_streaming_folder(self, uri):
        """
        Navigate into a Tidal/Qobuz/etc folder/category by emitting a browseLibrary request.
        """
        # If you have a socketIO connection, use it:
        if hasattr(self.display_manager, "volumio_listener") and hasattr(self.display_manager.volumio_listener, "fetch_browse_library"):
            self.display_manager.volumio_listener.fetch_browse_library(uri)
        else:
            # fallback to HTTP GET
            self.fetch_navigation(uri)


    def select_item(self):
        if not self.is_active or not self.current_menu_items:
            return
        selected = self.current_menu_items[self.current_selection_index]
        self.logger.info(f"[{self.service_type}] Selected item: {json.dumps(selected, indent=2)}")

        # --- Handle synthetic submenu actions first ---
        if "action" in selected:
            self.logger.info(f"[{self.service_type}] Performing album action: {selected['action']}")
            self.perform_action(selected["action"], selected.get("data", {}))
            return

        if selected["title"] == "Back":
            self.logger.debug(f"[{self.service_type}] 'Back' selected, returning to previous menu.")
            self.back()
            return

        item_type = selected.get("type", "")
        service = selected.get("service", self.service_type)
        uri = selected.get("uri", "")

        # --- Handle Tidal/Qobuz "item-no-menu": treat as folder if there's a URI ---
        if item_type == "item-no-menu":
            if uri:  # treat as a navigable folder, like old TidalManager
                self.logger.info(f"[{self.service_type}] Navigating into item-no-menu: '{selected.get('title')}' ({uri})")
                self.push_path(self.current_path)
                self.current_path = uri
                self.display_loading_screen()
                self.fetch_navigation(self.current_path)
                return
            else:  # block if truly not navigable
                self.logger.info(f"[{self.service_type}] '{selected.get('title','')}' is not selectable (type: {item_type}, no uri).")
                self.display_message("Not available", f"'{selected.get('title', '')}' cannot be opened.")
                return

        # --- (The rest is as before) ---
        unsupported_types = [
            "item-no-play", "divider", "header", "section", "none",
        ]
        if item_type in unsupported_types:
            self.logger.info(f"[{self.service_type}] '{selected.get('title','')}' is not selectable (type: {item_type}).")
            self.display_message("Not available", f"'{selected.get('title', '')}' cannot be opened.")
            return

        folder_types = [
            "folder", "album", "internal-folder", "usb-folder", "nas-folder", "album_folder",
            "streaming-category", "streaming-folder", "remdisk"
        ]
        song_types = [
            "song", "track", "audio", "file", "playlist", "album",
            "play_album", "play_song", "select_songs"
        ]

        # --- Streaming plugin handling (Tidal, Qobuz, etc) ---
        streaming_services = ("tidal", "qobuz", "deezer", "spotify")
        if service in streaming_services or (uri.startswith("tidal://") or uri.startswith("qobuz://")):
            # Play song directly if it's a track, or contains "/song/"
            if item_type == "song" or (uri and "/song/" in uri):
                self.logger.info(f"[{service}] Streaming plugin: playing song '{selected.get('title')}'")
                self.play_streaming_song(selected)
                return
            # Otherwise, treat as folder/category: navigate further
            if uri:
                self.logger.info(f"[{service}] Streaming plugin: navigating into '{selected.get('title')}' ({uri})")
                self.push_path(self.current_path)
                self.current_path = uri
                self.display_loading_screen()
                self.navigate_streaming_folder(uri)
                return
            self.display_message("Not available", f"'{selected.get('title', '')}' cannot be opened.")
            return

        self.logger.info(f"[{self.service_type}] Item type: '{item_type}'")
        if item_type in folder_types:
            if self.is_album_folder(selected):
                self.logger.info(f"[{self.service_type}] Detected album folder: '{selected.get('title')}'. Showing album options.")
                self.display_album_options(selected)
            else:
                self.logger.info(f"[{self.service_type}] Entering folder: '{selected.get('title')}'")
                self.push_path(self.current_path)
                self.current_path = selected["uri"]
                self.display_loading_screen()
                self.fetch_navigation(self.current_path)
        elif item_type in song_types or item_type == "webradio":
            self.logger.info(f"[{self.service_type}] Playing item: '{selected.get('title')}'")
            self.replace_and_play(selected)
        else:
            self.logger.warning(f"[{self.service_type}] Unknown type: {item_type}, item: {json.dumps(selected, indent=2)}")
            self.display_message("Unknown Type", f"Type: {item_type}")


    def is_album_folder(self, item):
        folder_uri = item.get("uri")
        if not folder_uri:
            return False
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/browse?uri={quote(folder_uri)}")
            items = resp.json().get("navigation", {}).get("lists", [{}])[0].get("items", [])
            has_songs = any(i.get("type", "") == "song" for i in items)
            has_folders = any(i.get("type", "") in ["folder", "album"] for i in items)
            self.logger.debug(f"[{self.service_type}] Album folder check for '{item.get('title', '')}': has_songs={has_songs}, has_folders={has_folders}")
            return has_songs and not has_folders
        except Exception as e:
            self.logger.error(f"[{self.service_type}] Exception in is_album_folder: {e}")
            return False

    def display_album_options(self, album_item):
        self.logger.info(f"[{self.service_type}] Displaying album options for album: {album_item.get('title', '')}")
        options = [
            {"title": "Play Album", "action": "play_album", "data": album_item},
            {"title": "Select Songs", "action": "select_songs", "data": album_item},
            {"title": "Back", "action": "back"}
        ]
        self.push_submenu(options, menu_title=f"Album: {album_item.get('title', '')}")

    def perform_action(self, action, data):
        self.logger.info(f"[{self.service_type}] Performing action: '{action}' on '{data.get('title', '')}'")
        if action == "play_album":
            self.play_album_or_folder(data)
        elif action == "select_songs":
            self.push_path(self.current_path)
            self.current_path = data.get("uri")
            self.display_loading_screen()
            self.fetch_navigation(self.current_path)
        elif action == "back":
            self.back()
        else:
            self.display_message("Invalid Action", action)

    def play_album_or_folder(self, folder_item):
        folder_uri = folder_item.get("uri")
        if not folder_uri:
            self.display_message("Playback Error", "No URI")
            return
        Thread(target=self._play_album_thread, args=(folder_uri, folder_item.get("title", "")), daemon=True).start()

    def _play_album_thread(self, album_uri, album_title):
        try:
            # Fetch the album's content (list all tracks)
            resp = self.session.get(f"{self.base_url}/api/v1/browse?uri={quote(album_uri)}")
            if resp.status_code != 200:
                self.display_message("Playback Error", f"Failed to fetch album: {resp.status_code}")
                return
            items = resp.json().get("navigation", {}).get("lists", [{}])[0].get("items", [])
            # Filter out only songs/tracks (you can tweak types as needed)
            track_uris = [
                item.get("uri")
                for item in items
                if item.get("type") in ("song", "track", "audio", "file") and item.get("uri")
            ]
            if not track_uris:
                self.display_message("Playback Error", f"No tracks found in {album_title}")
                return
            # Start playback with the first song
            first_track = track_uris[0]
            self.session.post(
                f"{self.base_url}/api/v1/replaceAndPlay",
                json={"name": album_title, "service": self.service_type, "uri": first_track}
            )
            # Optionally, queue the rest of the tracks (not strictly necessary but mirrors album play behaviour)
            for uri in track_uris[1:]:
                self.session.post(
                    f"{self.base_url}/api/v1/addToQueue",
                    json={"name": album_title, "service": self.service_type, "uri": uri}
                )
            self.display_message("Playback Started", f"Playing: {album_title}")
        except Exception as e:
            self.display_message("Playback Error", str(e))

    def replace_and_play(self, item):
        uri = item.get("uri")
        if not uri:
            self.display_message("Playback Error", "No URI")
            return
        try:
            url = f"{self.base_url}/api/v1/replaceAndPlay"
            data = {"name": item.get("title", ""), "service": item.get("service", self.service_type), "uri": uri}
            resp = self.session.post(url, json=data)
            if resp.status_code == 200:
                self.display_message("Playback Started", f"Playing: {item.get('title', '')}")
            else:
                self.display_message("Playback Error", f"Failed: {resp.status_code}")
        except Exception as e:
            self.display_message("Playback Error", str(e))

    def display_loading_screen(self):
        self.display_message("Loading...", "")

    def display_menu(self):
        if self.menu_stack and self.menu_stack[-1]["type"] == "submenu":
            menu_title = self.menu_stack[-1].get("menu_title", "Library")
        else:
            menu_title = self.current_path.split("/")[-1] if "/" in self.current_path else self.current_path
        visible_items = self.get_visible_window(self.current_menu_items)
        font = self.display_manager.fonts.get(self.font_key, ImageFont.load_default())

        def truncate(text, maxlen):
            return text if len(text) <= maxlen else text[:maxlen - 3] + "..."

        def draw(draw_obj):
            y = self.y_offset
            draw_obj.text((0, y), truncate(menu_title, 20), font=font, fill="yellow")
            y += self.line_spacing
            for i, item in enumerate(visible_items):
                idx = self.window_start_index + i
                if idx >= len(self.current_menu_items):
                    break
                arrow = "→ " if idx == self.current_selection_index else "  "
                fill = "white" if idx == self.current_selection_index else "gray"
                item_title = truncate(item.get("title", "Unknown"), 20)
                draw_obj.text((0, y + i * self.line_spacing), f"{arrow}{item_title}", font=font, fill=fill)
        self.display_manager.draw_custom(draw)

    def get_visible_window(self, items):
        if self.current_selection_index < self.window_start_index:
            self.window_start_index = self.current_selection_index
        elif self.current_selection_index >= self.window_start_index + self.window_size:
            self.window_start_index = self.current_selection_index - self.window_size + 1
        self.window_start_index = max(0, self.window_start_index)
        self.window_start_index = min(self.window_start_index, max(0, len(items) - self.window_size))
        return items[self.window_start_index: self.window_start_index + self.window_size]

    def scroll_selection(self, direction):
        if not self.is_active or not self.current_menu_items:
            return
        prev_index = self.current_selection_index
        self.current_selection_index += direction
        self.current_selection_index = max(0, min(self.current_selection_index, len(self.current_menu_items) - 1))
        self.display_menu()

    def display_message(self, title, message):
        font = self.display_manager.fonts.get(self.font_key, ImageFont.load_default())
        def draw(draw_obj):
            draw_obj.text((0, self.y_offset), title[:20], font=font, fill="yellow")
            draw_obj.text((0, self.y_offset + self.line_spacing), message[:20], font=font, fill="white")
        self.display_manager.draw_custom(draw)

    def push_submenu(self, menu_items, menu_title=""):
        self.menu_stack.append({
            "type": "submenu",
            "menu_items": self.current_menu_items.copy(),
            "selection_index": self.current_selection_index,
            "window_start_index": self.window_start_index,
            "menu_title": menu_title or "Options"
        })
        self.current_menu_items = menu_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self.display_menu()

    def push_path(self, path):
        self.menu_stack.append({"type": "path", "path": path})

    def back(self):
        if not self.menu_stack:
            self.stop_mode()
            self.mode_manager.back()
            return
        last = self.menu_stack.pop()
        if last["type"] == "submenu":
            self.current_menu_items = last["menu_items"]
            self.current_selection_index = last["selection_index"]
            self.window_start_index = last["window_start_index"]
            self.display_menu()
        elif last["type"] == "path":
            self.current_path = last["path"]
            self.display_loading_screen()
            self.fetch_navigation(self.current_path)

    # Optionally, add update_song_info and other UI utilities as needed
