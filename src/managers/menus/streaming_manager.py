# src/managers/streaming_manager.py

from managers.base_manager import BaseManager
import logging
from PIL import ImageFont
import threading

class StreamingManager(BaseManager):
    def __init__(self, display_manager, volumio_listener, mode_manager, service_name, root_uri, window_size=4, y_offset=2, line_spacing=15):
        super().__init__(display_manager, volumio_listener, mode_manager)
        self.service_name = service_name      # e.g., "tidal", "qobuz", "spotify"
        self.root_uri = root_uri              # e.g., "tidal://", "qobuz://", "spotify://"
        self.current_selection_index = 0
        self.font_key = 'menu_font'
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.info(f"{service_name.title()} StreamingManager initialised.")

        # Initialise state
        self.menu_stack = []
        self.current_menu_items = []
        self.is_active = False

        # Window/display settings
        self.window_size = window_size
        self.window_start_index = 0
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Timeout timer
        self.timeout_timer = None

        # Register mode change callback
        if hasattr(self.mode_manager, "add_on_mode_change_callback"):
            self.mode_manager.add_on_mode_change_callback(self.handle_mode_change)

    def start_mode(self):
        if self.is_active:
            self.logger.debug(f"{self.service_name.title()}Manager: Already active.")
            return

        self.logger.info(f"{self.service_name.title()}Manager: Starting mode.")
        self.is_active = True
        self.current_selection_index = 0
        self.window_start_index = 0

        # Connect signals
        self.volumio_listener.navigation_received.connect(self.handle_navigation)
        self.volumio_listener.toast_message_received.connect(self.handle_toast_message)
        self.volumio_listener.state_changed.connect(self.handle_state_change)
        self.volumio_listener.track_changed.connect(self.handle_track_change)

        self.display_loading_screen()
        self.fetch_navigation(self.root_uri)

        # Start timeout timer (e.g. 5 seconds)
        self.timeout_timer = threading.Timer(5.0, self.loading_timeout)
        self.timeout_timer.start()

    def loading_timeout(self):
        if not self.current_menu_items:
            self.logger.warning(f"{self.service_name.title()}Manager: Timeout reached, no navigation data received.")

            def draw(draw_obj):
                draw_obj.text(
                    (10, self.y_offset),
                    f"{self.service_name.title()} is not loading...",
                    font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                    fill="white"
                )
                draw_obj.text(
                    (10, self.y_offset + self.line_spacing),
                    "Have you logged in via Volumio?",
                    font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                    fill="white"
                )

            self.display_manager.draw_custom(draw)
            threading.Timer(3.0, self.mode_manager.to_menu).start()

    def stop_mode(self):
        if not self.is_active:
            self.logger.debug(f"{self.service_name.title()}Manager: Already inactive.")
            return
        self.is_active = False
        self.display_manager.clear_screen()
        self.logger.info(f"{self.service_name.title()}Manager: Stopped and cleared display.")

        # Disconnect signals (may need to be more robust in your signal library)
        try:
            self.volumio_listener.navigation_received.disconnect(self.handle_navigation)
            self.volumio_listener.toast_message_received.disconnect(self.handle_toast_message)
            self.volumio_listener.state_changed.disconnect(self.handle_state_change)
            self.volumio_listener.track_changed.disconnect(self.handle_track_change)
        except Exception:
            pass

        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

    def handle_mode_change(self, current_mode):
        if current_mode == self.service_name:
            self.start_mode()
        elif self.is_active:
            self.stop_mode()

    def fetch_navigation(self, uri):
        self.logger.info(f"{self.service_name.title()}Manager: Fetching navigation data for URI: {uri}")
        if self.volumio_listener.is_connected():
            try:
                self.volumio_listener.fetch_browse_library(uri)
            except Exception as e:
                self.logger.error(f"{self.service_name.title()}Manager: Could not fetch navigation: {e}")
                self.display_error_message("Navigation Error", f"Could not fetch navigation: {e}")
        else:
            self.display_error_message("Connection Error", "Not connected to Volumio.")

    def handle_navigation(self, sender, navigation, service, uri, **kwargs):
        if service != self.service_name:
            return  # Ignore navigation not for this service
        self.update_menu(navigation)

    def update_menu(self, navigation):
        # Cancel the timeout timer if it is still running
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

        if not navigation:
            self.display_no_items()
            return

        lists = navigation.get("lists", [])
        if not lists or not isinstance(lists, list):
            self.display_no_items()
            return

        combined_items = []
        for lst in lists:
            list_items = lst.get("items", [])
            if list_items:
                combined_items.extend(list_items)

        if not combined_items:
            self.display_no_items()
            return

        self.current_menu_items = [
            {
                "title": item.get("title", "Untitled"),
                "uri": item.get("uri", ""),
                "type": item.get("type", ""),
            }
            for item in combined_items
        ]
        self.current_menu_items.append({"title": "Back", "uri": None, "type": "back"})

        self.display_menu()

    def display_no_items(self):
        def draw(draw_obj):
            draw_obj.text(
                (10, self.y_offset),
                f"No {self.service_name.title()} Items Available",
                font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                fill="white"
            )
        self.display_manager.draw_custom(draw)

    def display_menu(self):
        visible_items = self.get_visible_window(self.current_menu_items)
        def draw(draw_obj):
            for i, item in enumerate(visible_items):
                actual_index = self.window_start_index + i
                arrow = "-> " if actual_index == self.current_selection_index else "   "
                title = item['title']
                draw_obj.text(
                    (10, self.y_offset + i * self.line_spacing),
                    f"{arrow}{title}",
                    font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                    fill="white" if actual_index == self.current_selection_index else "gray"
                )
        self.display_manager.draw_custom(draw)

    def get_visible_window(self, items):
        if self.current_selection_index < self.window_start_index:
            self.window_start_index = self.current_selection_index
        elif self.current_selection_index >= self.window_start_index + self.window_size:
            self.window_start_index = self.current_selection_index - self.window_size + 1
        self.window_start_index = max(0, self.window_start_index)
        self.window_start_index = min(self.window_start_index, max(0, len(items) - self.window_size))
        return items[self.window_start_index:self.window_start_index + self.window_size]

    def scroll_selection(self, direction):
        if not self.is_active:
            return
        prev_index = self.current_selection_index
        self.current_selection_index += direction
        self.current_selection_index = max(0, min(self.current_selection_index, len(self.current_menu_items) - 1))
        self.display_menu()

    def select_item(self):
        if not self.is_active or not self.current_menu_items:
            return

        selected_item = self.current_menu_items[self.current_selection_index]
        if selected_item.get("title") == "Back":
            self.back()
            return

        uri = selected_item.get("uri")
        if not uri:
            self.display_error_message("Invalid Selection", "Selected item has no URI.")
            return

        # Play song or navigate deeper
        item_type = selected_item.get("type", "").lower()
        if item_type == "song" or (uri and "/song/" in uri) or uri.endswith("/play"):
            self.play_song(uri)
            return

        self.navigate_to(uri)

    def play_song(self, uri):
        self.logger.info(f"{self.service_name.title()}Manager: Sending replaceAndPlay for URI: {uri}")
        if self.volumio_listener.is_connected():
            try:
                self.volumio_listener.socketIO.emit('replaceAndPlay', {
                    "item": {
                        "service": self.service_name,
                        "uri": uri
                    }
                })
            except Exception as e:
                self.display_error_message("Playback Error", f"Could not play track: {e}")
        else:
            self.display_error_message("Connection Error", "Not connected to Volumio.")

    def navigate_to(self, uri):
        # Push current menu context to stack for back functionality
        self.menu_stack.append({
            "menu_items": self.current_menu_items.copy(),
            "selection_index": self.current_selection_index,
            "window_start_index": self.window_start_index
        })
        self.display_loading_screen()
        self.fetch_navigation(uri)

    def go_back(self):
        if not self.menu_stack:
            self.stop_mode()
            return
        previous_context = self.menu_stack.pop()
        self.current_menu_items = previous_context["menu_items"]
        self.current_selection_index = previous_context["selection_index"]
        self.window_start_index = previous_context["window_start_index"]
        self.display_menu()

    def back(self):
        if self.menu_stack:
            self.go_back()
        else:
            if self.is_active:
                self.stop_mode()
            self.mode_manager.back()

    def handle_toast_message(self, sender, message, **kwargs):
        message_type = message.get("type", "")
        title = message.get("title", "")
        body = message.get("message", "")
        if message_type == "error":
            self.display_error_message(title, body)
        elif message_type == "success":
            pass  # Optionally display message
        else:
            pass

    def display_loading_screen(self):
        def draw(draw_obj):
            draw_obj.text(
                (10, self.y_offset),
                f"Loading {self.service_name.title()}...",
                font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                fill="white"
            )
        self.display_manager.draw_custom(draw)

    def display_error_message(self, title, message):
        def draw(draw_obj):
            draw_obj.text(
                (10, self.y_offset),
                f"Error: {title}",
                font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                fill="white"
            )
            draw_obj.text(
                (10, self.y_offset + self.line_spacing),
                message,
                font=self.display_manager.fonts.get(self.font_key, ImageFont.load_default()),
                fill="white"
            )
        self.display_manager.draw_custom(draw)

    def handle_state_change(self, sender, state, **kwargs):
        if state.get('service') == self.service_name:
            self.update_song_info(state)

    def handle_track_change(self, sender, track, **kwargs):
        if track.get('service') == self.service_name:
            self.update_song_info(track)

    def update_song_info(self, state):
        # Optionally display song info / metrics if you want
        pass
