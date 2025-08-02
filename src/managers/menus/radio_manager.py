# src/managers/radio_manager.py

import os
import logging
from PIL import Image, ImageDraw, ImageFont
import threading
import time
import requests
from io import BytesIO
from managers.base_manager import BaseManager

RADIO_CATEGORY_ORDER = [
    "BBC Radios",
    "Volumio Selection",
    "My Web Radios",
    "Favorite Radios",
    "Top 500 Radios",
    "By genre",
    "Local Radios",
    "By country",
    "Popular Radios",
    "Best Radios"
]

RADIO_CATEGORY_LABELS = {
    "BBC Radios": "BBC",
    "Volumio Selection": "Volumio\nSelection",
    "My Web Radios": "WebRadio",
    "Favorite Radios": "Favourites",
    "Top 500 Radios": "Top 500",
    "By genre": "Genre",
    "Local Radios": "Local",
    "By country": "Country",
    "Popular Radios": "Popular",
    "Best Radios": "Best"
}

CATEGORY_ICON_MAP = {
    "BBC Radios": "bbc.png",
    "Volumio Selection": "volumio.png",
    "My Web Radios": "ecg_heart.png",
    "Favorite Radios": "favorite.png",
    "Top 500 Radios": "star.png",
    "By genre": "sell.png",
    "Local Radios": "location.png",
    "By country": "globe.png",
    "Popular Radios": "recommend.png",
    "Best Radios": "diamond.png",
}

def order_radio_categories(api_items):
    item_map = {item['title']: item for item in api_items}
    ordered = [item_map[name] for name in RADIO_CATEGORY_ORDER if name in item_map]
    leftovers = [item for name, item in item_map.items() if name not in RADIO_CATEGORY_ORDER]
    return ordered + leftovers

class RadioManager(BaseManager):
    def __init__(self, display_manager, volumio_listener, mode_manager, window_size=4, y_offset=2, line_spacing=15):
        super().__init__(display_manager, volumio_listener, mode_manager)
        self.mode_name = "webradio"
        self.display_manager = display_manager
        self.volumio_listener = volumio_listener
        self.mode_manager = mode_manager

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.categories = []
        self.category_items = []
        self.stations = []
        self.current_selection_index = 0
        self.current_menu = "categories"
        self.font_key = 'menu_font'
        self.bold_font_key = 'menu_font_bold'
        self.font = self.display_manager.fonts.get(self.font_key, ImageFont.load_default())
        self.menu_stack = []
        self.is_active = False
        self.window_start_index = 0
        self.window_size = window_size
        self.y_offset = y_offset
        self.line_spacing = line_spacing
        self.last_requested_uri = None
        self.last_action_time = 0
        self.debounce_interval = 0.3
        self._signals_connected = False

    def connect_signals(self):
        if not self._signals_connected:
            try:
                self.volumio_listener.navigation_received.connect(self.handle_navigation)
                self.volumio_listener.toast_message_received.connect(self.handle_toast_message)
                self._signals_connected = True
                self.logger.debug("RadioManager: Connected to signals.")
            except Exception as e:
                self.logger.error(f"RadioManager: Failed to connect signals - {e}")

    def disconnect_signals(self):
        if self._signals_connected:
            try:
                self.volumio_listener.navigation_received.disconnect(self.handle_navigation)
                self.volumio_listener.toast_message_received.disconnect(self.handle_toast_message)
                self._signals_connected = False
                self.logger.debug("RadioManager: Disconnected from signals.")
            except Exception as e:
                self.logger.error(f"RadioManager: Failed to disconnect signals - {e}")

    def start_mode(self):
        if self.is_active:
            self.logger.debug("RadioManager: Radio mode already active.")
            return
        self.logger.info("RadioManager: Starting Radio mode.")
        self.is_active = True
        self.current_selection_index = 0
        self.window_start_index = 0
        self.current_menu = "categories"
        self.menu_stack.clear()
        self.stations.clear()
        self.connect_signals()
        self.fetch_radio_categories()

    def stop_mode(self):
        self.logger.info("RadioManager: Stopping Radio mode.")
        if not self.is_active:
            self.logger.warning("RadioManager: Mode is already inactive.")
            return
        self.is_active = False
        self.display_manager.clear_screen()
        self.disconnect_signals()

    def load_category_icon(self, category_title):
        icon_name = CATEGORY_ICON_MAP.get(category_title)
        if icon_name:
            local_path = f"/home/volumio/Quadify/src/assets/pngs/radioicons/{icon_name}"
            if os.path.exists(local_path):
                return Image.open(local_path).convert("RGBA")
        return self.display_manager.icons.get("webradio")


    def load_icon(self, icon_path):
        try:
            if not icon_path:
                return self.display_manager.icons.get("webradio")
            if icon_path.startswith("http"):
                response = requests.get(icon_path, timeout=2)
                if response.status_code == 200:
                    return Image.open(BytesIO(response.content)).convert("RGBA")
            elif icon_path.startswith("/"):
                png_name = os.path.basename(icon_path)
                local_path = f"/home/volumio/Quadify/src/assets/pngs/radioicons/{png_name}"
                if os.path.exists(local_path):
                    return Image.open(local_path).convert("RGBA")
            return self.display_manager.icons.get("webradio")
        except Exception as e:
            self.logger.warning(f"RadioManager: Could not load icon: {icon_path} - {e}")
        return self.display_manager.icons.get("webradio")

    def lookup_fontawesome_or_fallback(self, icon_str):
        icon_map = self.display_manager.icons
        if icon_str and "fa-" in icon_str:
            key = icon_str.replace("fa fa-", "").replace("-", "_").upper()
            return icon_map.get(key, icon_map.get("webradio"))
        return icon_map.get("webradio")

    def handle_navigation(self, sender, navigation, **kwargs):
        try:
            self.logger.debug(f"RadioManager: handle_navigation called with navigation={navigation}")
            if not navigation or not isinstance(navigation, dict):
                self.logger.error("RadioManager: Received invalid navigation data.")
                return
            if self.last_requested_uri == "radio":
                self.update_radio_categories(navigation)
                self.last_requested_uri = None
            elif self.last_requested_uri and self.current_menu == "stations":
                self.logger.info("RadioManager: Processing navigation data for Web Radio.")
                self.update_radio_stations(navigation)
                self.last_requested_uri = None
            else:
                self.logger.warning(f"RadioManager: Ignoring navigation for last_requested_uri: {self.last_requested_uri}")
        except Exception as e:
            self.logger.exception(f"RadioManager: Exception in handle_navigation - {e}")

    def update_radio_categories(self, navigation):
        try:
            self.logger.info("RadioManager: Updating radio categories.")
            lists = navigation.get("lists", [])
            items = []
            for lst in lists:
                lst_items = lst.get("items", [])
                if lst_items:
                    items.extend(lst_items)
            if not items:
                self.display_no_categories_message()
                return
            self.category_items = items
            ordered_items = order_radio_categories(items)
            self.categories = [
                {
                    "title": item.get("title", item.get("name", "Untitled")),
                    "uri": item.get("uri"),
                    "albumart": item.get("albumart", None),
                    "icon": item.get("icon", None),
                }
                for item in ordered_items
            ]
            self.categories.append({"title": "Back", "icon": None, "albumart": None, "uri": None})
            self.logger.info(f"RadioManager: Updated categories list with {len(self.categories)} items.")
            self.current_selection_index = 0
            self.window_start_index = 0
            self.draw_categories_horizontal()
        except Exception as e:
            self.logger.exception(f"RadioManager: Exception in update_radio_categories - {e}")
            self.display_error_message("Error", "Failed to update categories.")

    def draw_categories_horizontal(self):
        visible_items = self.get_visible_window(self.categories)
        icon_size = 30
        spacing = 25
        total_width = self.display_manager.oled.width
        total_height = self.display_manager.oled.height
        total_icons_width = len(visible_items) * icon_size + (len(visible_items) - 1) * spacing
        x_offset = (total_width - total_icons_width) // 2
        y_position = (total_height - icon_size) // 2 - 10

        base_image = Image.new("RGB", self.display_manager.oled.size, "black")
        draw_obj = ImageDraw.Draw(base_image)

        for i, cat in enumerate(visible_items):
            actual_index = self.window_start_index + i
            icon_img = self.load_category_icon(cat["title"])
            if icon_img.mode != "RGBA":
                icon_img = icon_img.convert("RGBA")
            icon_img = icon_img.resize((icon_size, icon_size), Image.LANCZOS)
            x = x_offset + i * (icon_size + spacing)
            y_adjustment = -5 if actual_index == self.current_selection_index else 0
            base_image.paste(icon_img, (x, y_position + y_adjustment), icon_img)
            # Draw the stacked label
            label = RADIO_CATEGORY_LABELS.get(cat["title"], cat["title"])
            font = self.display_manager.fonts.get(
                self.font_key if actual_index == self.current_selection_index else self.font_key,
                ImageFont.load_default(),
            )
            text_color = "white" if actual_index == self.current_selection_index else "black"
            lines = label.split('\n')
            for l_idx, line in enumerate(lines):
                tw, th = draw_obj.textsize(line, font=font)
                text_x = x + (icon_size - tw) // 2
                text_y = y_position + icon_size - 2 + l_idx * (th + 1)
                draw_obj.text((text_x, text_y), line, font=font, fill=text_color)
        base_image = base_image.convert(self.display_manager.oled.mode)
        self.display_manager.oled.display(base_image)

    def display_radio_stations(self):
        self.logger.info("RadioManager: Displaying radio stations.")
        if not self.stations:
            self.display_no_stations_message()
            return
        def draw(draw_obj):
            visible_stations = self.get_visible_window([station['title'] for station in self.stations])
            y_offset = self.y_offset
            x_offset_arrow = 5
            for i, station_title in enumerate(visible_stations):
                actual_index = self.window_start_index + i
                arrow = "-> " if actual_index == self.current_selection_index else "   "
                fill_color = "white" if actual_index == self.current_selection_index else "gray"
                draw_obj.text(
                    (x_offset_arrow, y_offset + i * self.line_spacing),
                    f"{arrow}{station_title}",
                    font=self.font,
                    fill=fill_color
                )
        self.display_manager.draw_custom(draw)
        self.logger.debug("RadioManager: Stations displayed within the visible window.")

    def update_radio_stations(self, navigation):
        try:
            self.logger.info("RadioManager: Updating radio stations.")
            lists = navigation.get("lists", [])
            if not lists or not isinstance(lists, list):
                self.logger.warning("RadioManager: No valid lists received for stations.")
                self.display_no_stations_message()
                return
            items = []
            for lst in lists:
                lst_items = lst.get("items", [])
                if lst_items:
                    items.extend(lst_items)
            if not items:
                self.logger.info("RadioManager: No stations in navigation. Displaying 'No Stations Available'.")
                self.display_no_stations_message()
                return
            self.stations = [
                {
                    "title": item.get("title", item.get("name", "Untitled")),
                    "uri": item.get("uri", item.get("link", "")),
                    "albumart": item.get("albumart", ""),
                }
                for item in items
            ]
            self.stations.append({"title": "Back", "uri": None})
            self.logger.info(f"RadioManager: Updated stations list with {len(self.stations)} items.")
            self.current_selection_index = 0
            self.window_start_index = 0
            self.display_radio_stations()
        except Exception as e:
            self.logger.exception(f"RadioManager: Exception in update_radio_stations - {e}")
            self.display_error_message("Error", "Failed to update stations.")

    def display_no_categories_message(self):
        self.logger.info("RadioManager: Displaying 'No Categories Available' message.")
        def draw(draw_obj):
            text = "No Categories Available."
            font = self.font
            width, height = draw_obj.textsize(text, font=font)
            image_width, image_height = draw_obj.im.size
            x = (image_width - width) // 2
            y = (image_height - height) // 2
            draw_obj.text((x, y), text, font=font, fill="white")
        self.display_manager.draw_custom(draw)
        self.logger.debug("RadioManager: 'No Categories Available' message displayed.")

    def display_no_stations_message(self):
        self.logger.info("RadioManager: Displaying 'No Stations Available' message.")
        def draw(draw_obj):
            text = "No Stations Available."
            font = self.font
            width, height = draw_obj.textsize(text, font=font)
            image_width, image_height = draw_obj.im.size
            x = (image_width - width) // 2
            y = (image_height - height) // 2
            draw_obj.text((x, y), text, font=font, fill="white")
        self.display_manager.draw_custom(draw)
        self.logger.debug("RadioManager: 'No Stations Available' message displayed.")

    def scroll_selection(self, direction):
        if not self.is_active:
            self.logger.warning("RadioManager: Scroll attempted while inactive.")
            return
        current_time = time.time()
        if current_time - self.last_action_time < self.debounce_interval:
            self.logger.debug("RadioManager: Scroll action ignored due to debounce.")
            return
        self.last_action_time = current_time
        if self.current_menu == "categories":
            options = self.categories
        elif self.current_menu == "stations":
            options = [station['title'] for station in self.stations]
        else:
            self.logger.warning("RadioManager: Unknown menu state.")
            return
        if not options:
            self.logger.warning("RadioManager: No options available to scroll.")
            return
        previous_index = self.current_selection_index
        if isinstance(direction, int) and direction > 0:
            if self.current_selection_index < len(options) - 1:
                self.current_selection_index += 1
        elif isinstance(direction, int) and direction < 0:
            if self.current_selection_index > 0:
                self.current_selection_index -= 1
        else:
            self.logger.warning("RadioManager: Invalid scroll direction provided.")
            return
        if previous_index != self.current_selection_index:
            self.logger.debug(f"RadioManager: Scrolled to index: {self.current_selection_index}")
            if self.current_menu == "categories":
                self.draw_categories_horizontal()
            elif self.current_menu == "stations":
                self.display_radio_stations()
        else:
            self.logger.debug("RadioManager: Reached the end/start of the list. Scroll input ignored.")

    def select_item(self):
        if not self.is_active:
            self.logger.warning("RadioManager: Select attempted while inactive.")
            return
        current_time = time.time()
        if current_time - self.last_action_time < self.debounce_interval:
            self.logger.debug("RadioManager: Select action ignored due to debounce.")
            return
        self.last_action_time = current_time
        if self.current_menu == "categories":
            selected_category = self.categories[self.current_selection_index]
            self.logger.info(f"RadioManager: Selected radio category: {selected_category}")
            if isinstance(selected_category, dict) and selected_category.get("title") == "Back":
                self.navigate_back()
                return
            uri = selected_category.get("uri")
            if uri:
                self.logger.info(
                    f"RadioManager: Fetching radio stations for category '{selected_category.get('title', '')}' with URI '{uri}'"
                )
                self.fetch_radio_stations(uri)
                self.menu_stack.append("categories")
                self.current_menu = "stations"
                self.current_selection_index = 0
                self.window_start_index = 0
            else:
                self.logger.error(f"RadioManager: No URI found for category '{selected_category}'")
                self.display_error_message("Error", f"No URI found for category '{selected_category}'")
        elif self.current_menu == "stations":
            if not self.stations:
                self.logger.error("RadioManager: No stations available to select.")
                return
            selected_station = self.stations[self.current_selection_index]
            station_title = selected_station.get('title', '').strip()
            if station_title == "Back":
                self.navigate_back()
                return
            uri = selected_station.get('uri')
            albumart_url = selected_station.get('albumart', '')
            self.logger.info(f"RadioManager: Attempting to play station: {station_title} with URI: {uri}")
            self.play_station(station_title, uri, albumart_url=albumart_url)
        else:
            self.logger.warning("RadioManager: Unknown menu state.")

    def navigate_back(self):
        if not self.is_active:
            self.logger.warning("RadioManager: Back navigation attempted while inactive.")
            return
        current_time = time.time()
        if current_time - self.last_action_time < self.debounce_interval:
            self.logger.debug("RadioManager: Back action ignored due to debounce.")
            return
        self.last_action_time = current_time
        if not self.menu_stack:
            self.logger.info("RadioManager: No previous menu to navigate back to. Exiting Radio mode.")
            self.stop_mode()
            return
        self.current_menu = self.menu_stack.pop()
        self.current_selection_index = 0
        self.window_start_index = 0
        if self.current_menu == "categories":
            self.draw_categories_horizontal()
        elif self.current_menu == "stations":
            self.display_radio_stations()

    def back(self):
        if self.menu_stack:
            self.navigate_back()
        else:
            if self.is_active:
                self.stop_mode()
            self.mode_manager.back()

    def get_visible_window(self, items):
        total_items = len(items)
        half_window = self.window_size // 2
        tentative_start = self.current_selection_index - half_window
        if tentative_start < 0:
            self.window_start_index = 0
        elif tentative_start + self.window_size > total_items:
            self.window_start_index = max(total_items - self.window_size, 0)
        else:
            self.window_start_index = tentative_start
        visible_items = items[self.window_start_index:self.window_start_index + self.window_size]
        self.logger.debug(
            f"RadioManager: Visible window indices {self.window_start_index} to "
            f"{self.window_start_index + self.window_size -1}"
        )
        return visible_items

    def fetch_radio_categories(self):
        self.logger.info("RadioManager: Fetching radio categories.")
        if self.volumio_listener.is_connected():
            try:
                self.last_requested_uri = "radio"
                self.volumio_listener.fetch_browse_library("radio")
                self.logger.info("RadioManager: Emitted 'browseLibrary' for 'radio' URI.")
            except Exception as e:
                self.logger.error(f"RadioManager: Failed to fetch radio categories - {e}")
                self.display_error_message("Navigation Error", f"Could not fetch radio categories: {e}")
        else:
            self.logger.warning("RadioManager: Cannot fetch radio categories - not connected to Volumio.")
            self.display_error_message("Connection Error", "Not connected to Volumio.")

    def fetch_radio_stations(self, uri):
        self.logger.info(f"RadioManager: Fetching radio stations for URI: {uri}")
        if self.volumio_listener.is_connected():
            try:
                self.last_requested_uri = uri
                self.volumio_listener.fetch_browse_library(uri)
                self.logger.info(f"RadioManager: Emitted 'browseLibrary' for URI: {uri}")
            except Exception as e:
                self.logger.error(f"RadioManager: Failed to emit 'browseLibrary' for {uri}: {e}")
                self.display_error_message("Navigation Error", f"Could not fetch radio stations: {e}")
        else:
            self.logger.warning("RadioManager: Cannot fetch radio stations - not connected to Volumio.")
            self.display_error_message("Connection Error", "Not connected to Volumio.")

    def get_category_item_by_title(self, title):
        for item in self.category_items:
            if item.get("title", "") == title:
                return item
        return None

    def play_station(self, title, uri, albumart_url=None):
        try:
            self.logger.info(f"RadioManager: Attempting to play Web Radio: {title}")
            self.logger.debug(f"RadioManager: Stream URI: {uri}")
            if self.volumio_listener.is_connected():
                try:
                    self.mode_manager.suppress_state_change()
                    self.logger.debug("RadioManager: Suppressed state changes.")
                    payload = {
                        'title': title,
                        'service': 'webradio',
                        'uri': uri,
                        'type': 'webradio',
                        'albumart': albumart_url if albumart_url else '',
                        'icon': 'fa fa-music',
                    }
                    self.logger.debug(f"RadioManager: Payload to send: {payload}")
                    self.volumio_listener.socketIO.emit('replaceAndPlay', payload)
                    self.logger.info(f"RadioManager: Sent replaceAndPlay command with URI: {uri}")
                    threading.Timer(1.0, self.mode_manager.allow_state_change).start()
                    self.logger.debug("RadioManager: Allowed state changes after delay.")
                except Exception as e:
                    self.logger.error(f"RadioManager: Failed to emit replaceAndPlay - {e}")
                    self.display_error_message("Playback Error", f"Could not emit play command: {e}")
            else:
                self.logger.warning("RadioManager: Cannot play station - not connected to Volumio.")
                self.display_error_message("Connection Error", "Not connected to Volumio.")
        except Exception as e:
            self.logger.exception(f"RadioManager: Unexpected error in play_station - {e}")
            self.display_error_message("Unexpected Error", f"An unexpected error occurred: {e}")

    def display_error_message(self, title, message):
        self.logger.error(f"{title}: {message}")
        def draw(draw_obj):
            text = f"{title}\n{message}"
            font = self.font
            y_offset = 10
            for line in text.split('\n'):
                draw_obj.text((10, y_offset), line, font=font, fill="white")
                y_offset += self.line_spacing
        self.display_manager.draw_custom(draw)
        self.logger.debug(f"RadioManager: Displayed error message '{title}: {message}' on OLED.")

    def handle_toast_message(self, sender, message):
        try:
            message_type = message.get("type", "").lower()
            title = message.get("title", "Message")
            body = message.get("message", "")
            if message_type == "error":
                self.logger.error(f"RadioManager: Error received - {title}: {body}")
                if body.lower() == "no results" and self.current_menu == "stations":
                    self.logger.info("RadioManager: No results for stations. Displaying message.")
                    self.display_no_stations_message()
                else:
                    self.display_error_message("Error", body)
            elif message_type == "success":
                self.logger.info(f"RadioManager: Success - {title}: {body}")
            else:
                self.logger.info(f"RadioManager: Received toast message - {title}: {body}")
        except Exception as e:
            self.logger.exception(f"RadioManager: Exception in handle_toast_message - {e}")

    def update_song_info(self, state):
        self.logger.info("PlaybackManager: Updating playback metrics display.")
        sample_rate = state.get("samplerate", "Unknown Sample Rate")
        bitdepth = state.get("bitdepth", "Unknown Bit Depth")
        volume = state.get("volume", "Unknown Volume")
        self.mode_manager.playback_manager.update_playback_metrics(state)
