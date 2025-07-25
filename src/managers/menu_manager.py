import logging
from PIL import Image, ImageDraw, ImageFont
import threading
import time

class MenuManager:
    def __init__(self, display_manager, volumio_listener, mode_manager, window_size=5, menu_type="icon_row"):
        self.display_manager = display_manager
        self.volumio_listener = volumio_listener
        self.mode_manager = mode_manager

        # Initialize logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.info("MenuManager initialized.")

        # Menu setup
        self.menu_stack = []
        self.current_menu_items = ["Stream", "Library", "Playlists", "Radio", "Config"]
        self.stream_menu_items = ["Tidal", "Qobuz", "Spotify", "MotherE", "RadioP"]
        self.library_menu_items = ["INTERNAL", "NAS", "USB"]
        self.display_menu_items = ["Display", "Screensavers", "Clock", "Contrast"]
        self.icons = {
            "Stream": self.display_manager.icons.get("stream"),
            "Library": self.display_manager.icons.get("library"),
            "Radio": self.display_manager.icons.get("webradio"),
            "RadioP": self.display_manager.icons.get("radio_paradise"),
            "MotherE": self.display_manager.icons.get("motherearthradio"),
            "Playlists": self.display_manager.icons.get("playlists"),
            "Tidal": self.display_manager.icons.get("tidal"),
            "Qobuz": self.display_manager.icons.get("qobuz"),
            "Spotify": self.display_manager.icons.get("spop"),
            "INTERNAL": self.display_manager.icons.get("mpd"),
            "NAS": self.display_manager.icons.get("nas"), 
            "USB": self.display_manager.icons.get("usb"),
            "Config": self.display_manager.icons.get("config"),
            "Original": self.display_manager.icons.get("display"),
            "Modern": self.display_manager.icons.get("display")
        }
        self.current_selection_index = 0
        self.is_active = False
        self.window_size = window_size
        self.window_start_index = 0
        self.menu_type = menu_type
        self.font_key = 'menu_font'
        self.bold_font_key = 'menu_font_bold'
        self.lock = threading.Lock()

        # Register mode change callback if available
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
        self.current_menu_items = ["Stream", "Library", "Playlists", "Radio", "Config"]
        self.current_selection_index = 0
        self.window_start_index = 0
        if not skip_initial_draw:
            threading.Thread(target=self.display_menu, daemon=True).start()

    def stop_mode(self):
        if not self.is_active:
            return
        self.is_active = False
        with self.lock:
            self.display_manager.clear_screen()
        self.logger.info("MenuManager: Stopped menu mode and cleared display.")

    # ----------- ANIMATION & DRAWING -----------

    def draw_menu(self, offset_x=0):
        with self.lock:
            visible_items = self.get_visible_window(self.current_menu_items, self.window_size)
            icon_size = 30
            spacing = 15
            total_width = self.display_manager.oled.width
            total_height = self.display_manager.oled.height
            total_icons_width = len(visible_items) * icon_size + (len(visible_items) - 1) * spacing
            x_offset = (total_width - total_icons_width) // 2 + offset_x
            y_position = (total_height - icon_size) // 2 - 10

            base_image = Image.new("RGB", self.display_manager.oled.size, "black")
            draw_obj = ImageDraw.Draw(base_image)

            for i, item in enumerate(visible_items):
                actual_index = self.window_start_index + i
                icon = self.icons.get(item, self.display_manager.default_icon)
                if icon.mode == "RGBA":
                    background = Image.new("RGB", icon.size, (0, 0, 0))
                    background.paste(icon, mask=icon.split()[3])
                    icon = background
                icon = icon.resize((icon_size, icon_size), Image.ANTIALIAS)
                x = x_offset + i * (icon_size + spacing)
                y_adjustment = -5 if actual_index == self.current_selection_index else 0
                base_image.paste(icon, (x, y_position + y_adjustment))
                label = item
                font = self.display_manager.fonts.get(
                    self.bold_font_key if actual_index == self.current_selection_index else self.font_key, ImageFont.load_default())
                text_color = "white" if actual_index == self.current_selection_index else "black"
                text_width, text_height = draw_obj.textsize(label, font=font)
                text_x = x + (icon_size - text_width) // 2
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
        self.display_menu()  # Ensure menu lands at offset 0

    def display_menu(self):
        self.draw_menu(offset_x=0)

    # ----------- MENU LOGIC -----------

    def config_menu(self):
        self.logger.info("MenuManager: Entering Config menu.")
        self.current_menu_items = ["Option 1", "Option 2", "Back"]
        self.current_selection_index = 0
        self.window_start_index = 0
        self.display_menu()

    def get_visible_window(self, items, window_size):
        half_window = window_size // 2
        self.window_start_index = self.current_selection_index - half_window
        if self.window_start_index < 0:
            self.window_start_index = 0
        elif self.window_start_index + window_size > len(items):
            self.window_start_index = max(len(items) - window_size, 0)
        return items[self.window_start_index:self.window_start_index + window_size]

    def scroll_selection(self, direction):
        if not self.is_active:
            return
        previous_index = self.current_selection_index
        self.current_selection_index += direction
        self.current_selection_index = max(0, min(self.current_selection_index, len(self.current_menu_items) - 1))
        self.logger.info(
            f"MenuManager: Scrolled from {previous_index} to {self.current_selection_index}. "
            f"Current menu items: {self.current_menu_items}"
        )
        self.window_start_index = self.current_selection_index - self.window_size // 2
        self.window_start_index = max(0, min(self.window_start_index, len(self.current_menu_items) - self.window_size))
        self.display_menu()

    def select_item(self):
        if not self.is_active or not self.current_menu_items:
            return
        selected_item = self.current_menu_items[self.current_selection_index]
        self.logger.info(f"MenuManager: Selected menu item: {selected_item}")
        threading.Thread(target=self._handle_selection, args=(selected_item,), daemon=True).start()

    def _handle_selection(self, selected_item):
        time.sleep(0.2)
        if selected_item == "Radio":
            self.mode_manager.to_radiomanager()
        elif selected_item == "Playlists":
            self.mode_manager.to_playlists()
        elif selected_item == "Stream":
            self.menu_stack.append(self.current_menu_items)
            self.current_menu_items = self.stream_menu_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self.display_menu()
        elif selected_item == "Library":
            self.menu_stack.append(self.current_menu_items)
            self.current_menu_items = self.library_menu_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self.display_menu()
        elif selected_item == "Config":
            self.menu_stack.append(self.current_menu_items)
            self.current_menu_items = self.display_menu_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self.config_menu()
        if selected_item == "Original":
            self.mode_manager.to_original()
            self.logger.info("MenuManager: Switching to FM4 screen.")
            self.mode_manager.to_menu()
        elif selected_item == "Modern":
            self.mode_manager.to_modern()
            self.logger.info("MenuManager: Switching to Modern screen.")
            self.mode_manager.to_menu()
        elif selected_item == "NAS":
            self.mode_manager.to_library(start_uri="music-library/NAS")
            self.logger.info("Library Manager for NAS activated.")
        elif selected_item == "INTERNAL":
            self.mode_manager.to_internal(start_uri="music-library/INTERNAL")
            self.logger.info("Internal Manager activated.")
        elif selected_item == "USB":
            self.mode_manager.to_library(start_uri="music-library/USB")
            self.logger.info("USB Library Manager activated.")
        elif selected_item == "Tidal":
            self.mode_manager.to_tidal()
        elif selected_item == "Qobuz":
            self.mode_manager.to_qobuz()
        elif selected_item == "RadioP":
            self.mode_manager.to_radioparadise()
        elif selected_item == "MotherE":
            self.mode_manager.to_motherearthradio()
        elif selected_item == "Spotify":
            self.mode_manager.to_spotify()
        elif selected_item == "Config":
            self.mode_manager.to_configmenu()

    # Add this method to your MenuManager class:

    def render_to_image(self, offset_x=0):
        """
        Renders the current menu to an Image, applying a horizontal offset for animation.
        """
        # Generate the menu image just like in display_icon_row_menu,
        # but instead of displaying it, return the image
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
            icon = self.icons.get(item, self.display_manager.default_icon)
            if icon.mode == "RGBA":
                background = Image.new("RGB", icon.size, (0, 0, 0))
                background.paste(icon, mask=icon.split()[3])
                icon = background
            icon = icon.resize((icon_size, icon_size), Image.ANTIALIAS)
            x = x_offset + i * (icon_size + spacing)
            y_adjustment = -5 if actual_index == self.current_selection_index else 0
            base_image.paste(icon, (x, y_position + y_adjustment))
            # Draw label
            label = item
            font = self.display_manager.fonts.get(self.bold_font_key if actual_index == self.current_selection_index else self.font_key, ImageFont.load_default())
            text_color = "white" if actual_index == self.current_selection_index else "black"
            text_width, text_height = draw_obj.textsize(label, font=font)
            text_x = x + (icon_size - text_width) // 2
            text_y = y_position + icon_size + 2
            draw_obj.text((text_x, text_y), label, font=font, fill=text_color)

        return base_image
