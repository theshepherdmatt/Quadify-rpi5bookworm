import logging
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from managers.menus.base_manager import BaseManager

class ConfigMenu(BaseManager):
    """
    A configuration menu displayed as a horizontal icon row.
    It matches the style of the MenuManager's icon row menu.
    """
    def __init__(self, display_manager, mode_manager, window_size=5):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Menu state
        self.is_active = False
        self.current_index = 0
        self.window_start_index = 0
        self.window_size = window_size
        self.lock = threading.Lock()

        # Fonts – use the same keys as in MenuManager
        self.font_key = 'menu_font'
        self.bold_font_key = 'menu_font_bold'

        # Define config menu items
        self.menu_items = [
            "Display",
            "System",
            "Update",
            "Back"
        ]

        # Map each menu item to an icon.
        # The keys for display_manager.icons should match your asset names.
        self.icons = {
            "Display": self.display_manager.icons.get("displaysettings"),
            "System": self.display_manager.icons.get("systeminfo"),
            "Update": self.display_manager.icons.get("systemupdate"),
            "Back": self.display_manager.icons.get("back")  # Use an appropriate icon
        }

    def get_visible_window(self, items, window_size):
        # Center the current selection in the visible window
        half_window = window_size // 2
        self.window_start_index = self.current_index - half_window
        if self.window_start_index < 0:
            self.window_start_index = 0
        elif self.window_start_index + window_size > len(items):
            self.window_start_index = max(len(items) - window_size, 0)
        return items[self.window_start_index:self.window_start_index + window_size]

    def start_mode(self):
        if self.is_active:
            self.logger.debug("ConfigMenu: already active.")
            return
        self.is_active = True
        self.current_index = 0
        self.window_start_index = 0
        self.logger.info("ConfigMenu: Starting config menu (icon row mode).")
        threading.Thread(target=self.display_menu, daemon=True).start()

    def stop_mode(self):
        if self.is_active:
            self.is_active = False
            with self.lock:
                self.display_manager.clear_screen()
            self.logger.info("ConfigMenu: Stopped config menu and cleared display.")

    def display_menu(self):
        with self.lock:
            # Use the same horizontal layout as MenuManager's icon row
            visible_items = self.get_visible_window(self.menu_items, self.window_size)

            # Constants for layout (matching MenuManager)
            icon_size = 30      # Fixed icon size
            spacing = 15        # Fixed spacing between icons
            total_width = self.display_manager.oled.width
            total_height = self.display_manager.oled.height

            # Calculate total width for the visible icons (icon size plus spacing)
            total_icons_width = len(visible_items) * icon_size + (len(visible_items) - 1) * spacing
            x_offset = (total_width - total_icons_width) // 2
            # Vertical position – centred with a slight upward adjustment
            y_position = (total_height - icon_size) // 2 - 10

            # Create an image to draw on
            base_image = Image.new("RGB", (total_width, total_height), "black")
            draw_obj = ImageDraw.Draw(base_image)

            # Iterate over visible items and draw icons with labels
            for i, item in enumerate(visible_items):
                actual_index = self.window_start_index + i
                icon = self.icons.get(item, self.display_manager.default_icon)

                # Handle transparency if the icon is RGBA
                if icon.mode == "RGBA":
                    background = Image.new("RGB", icon.size, (0, 0, 0))
                    background.paste(icon, mask=icon.split()[3])
                    icon = background

                # Resize the icon
                icon = icon.resize((icon_size, icon_size), Image.ANTIALIAS)

                # Calculate the x-coordinate for this icon
                x = x_offset + i * (icon_size + spacing)
                # If the icon is selected, “pop it out” slightly
                y_adjustment = -5 if actual_index == self.current_index else 0

                base_image.paste(icon, (x, y_position + y_adjustment))

                # Draw the label below the icon using bold font for selected items
                label = item
                font = self.display_manager.fonts.get(
                    self.bold_font_key if actual_index == self.current_index else self.font_key,
                    ImageFont.load_default()
                )
                text_color = "white" if actual_index == self.current_index else "black"

                text_width, text_height = draw_obj.textsize(label, font=font)
                text_x = x + (icon_size - text_width) // 2
                text_y = y_position + icon_size + 2
                draw_obj.text((text_x, text_y), label, font=font, fill=text_color)

            # Convert and display the image on the OLED
            base_image = base_image.convert(self.display_manager.oled.mode)
            self.display_manager.oled.display(base_image)
            self.logger.info("ConfigMenu: Icon row menu displayed.")

    def scroll_selection(self, direction):
        if not self.is_active:
            self.logger.warning("ConfigMenu: Attempted scroll while inactive.")
            return

        old_index = self.current_index
        self.current_index += direction
        self.current_index = max(0, min(self.current_index, len(self.menu_items) - 1))

        # Adjust the window to keep the selection centred if possible
        self.window_start_index = self.current_index - self.window_size // 2
        if self.window_start_index < 0:
            self.window_start_index = 0
        elif self.window_start_index + self.window_size > len(self.menu_items):
            self.window_start_index = max(len(self.menu_items) - self.window_size, 0)

        if old_index != self.current_index:
            self.logger.debug(f"ConfigMenu: Scrolled from {old_index} to {self.current_index}.")
            self.display_menu()

    def select_item(self):
        if not self.is_active:
            self.logger.warning("ConfigMenu: Attempted select while inactive.")
            return

        selected = self.menu_items[self.current_index]
        self.logger.info(f"ConfigMenu: Selected {selected}.")
        self.stop_mode()

        # Trigger the corresponding mode change
        if selected == "Display":
            self.mode_manager.to_displaymenu()
        elif selected == "System":
            self.mode_manager.to_systeminfo()
        elif selected == "Update":
            self.mode_manager.to_systemupdate()
        elif selected == "Back":
            self.mode_manager.to_menu()
        else:
            self.logger.warning(f"ConfigMenu: Unrecognised selection: {selected}")

    def back(self):
        if self.is_active:
            self.stop_mode()
        self.mode_manager.to_menu()
