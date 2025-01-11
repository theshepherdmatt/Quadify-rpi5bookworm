# src/menus/config_menu.py
import logging
import time
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class ConfigMenu(BaseManager):
    """
    A text-list (or icon) menu for picking configuration sub-menus:
      - Display
      - Clock
      - Screensaver
      - Contrast
      - SystemInfo
    """

    def __init__(self, display_manager, mode_manager,
                 window_size=5, y_offset=2, line_spacing=15):
        super().__init__(display_manager, None, mode_manager)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_active = False

        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        # The list of menu items
        self.menu_items = [
            "Display Settings",
            "Clock Settings",
            "Screensaver Settings",
            "System Info",
            "Back"
        ]
        self.current_index = 0

        # Basic layout stuff
        self.window_size  = window_size
        self.y_offset     = y_offset
        self.line_spacing = line_spacing

        # Debounce
        self.last_action_time = 0
        self.debounce_interval = 0.3

    def start_mode(self):
        if self.is_active:
            self.logger.debug("ConfigMenu: already active.")
            return
        self.is_active = True
        self.logger.info("ConfigMenu: Starting config menu.")
        self.display_items()

    def stop_mode(self):
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("ConfigMenu: Stopped and cleared display.")

    def display_items(self):
        """Renders the current menu items, highlighting the selected index."""
        def draw(draw_obj):
            for i, name in enumerate(self.menu_items):
                arrow = "-> " if i == self.current_index else "   "
                fill_color = "white" if i == self.current_index else "gray"
                y_pos = self.y_offset + i * self.line_spacing
                draw_obj.text(
                    (5, y_pos),
                    f"{arrow}{name}",
                    font=self.font,
                    fill=fill_color
                )
        self.display_manager.draw_custom(draw)
        self.logger.debug(f"ConfigMenu: Displayed items: {self.menu_items}")

    def scroll_selection(self, direction):
        if not self.is_active:
            self.logger.warning("ConfigMenu: Attempted scroll while inactive.")
            return
        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            return
        self.last_action_time = now

        old_index = self.current_index
        self.current_index += direction
        self.current_index = max(0, min(self.current_index, len(self.menu_items)-1))

        if old_index != self.current_index:
            self.logger.debug(f"ConfigMenu: scrolled from {old_index} to {self.current_index}")
            self.display_items()

    def select_item(self):
        """User selects the current item."""
        if not self.is_active:
            self.logger.warning("ConfigMenu: Attempted select while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            return
        self.last_action_time = now

        selected = self.menu_items[self.current_index]
        self.logger.info(f"ConfigMenu: Selected => {selected}")

        if selected == "Display Settings":
            # Jump to or start display menu
            self.stop_mode()
            self.mode_manager.to_displaymenu()

        elif selected == "Clock Settings":
            self.stop_mode()
            self.mode_manager.to_clockmenu()

        elif selected == "Screensaver Settings":
            self.stop_mode()
            self.mode_manager.to_screensavermenu()

        elif selected == "System Info":
            self.stop_mode()
            self.mode_manager.to_systeminfo()

        elif selected == "Back":
            self.stop_mode()
            self.mode_manager.to_menu()  # or return to main?

        else:
            self.logger.warning(f"Unrecognized config option: {selected}")

    def _open_contrast_menu(self):
        """
        Possibly open a mini-menu for brightness levels:
        e.g. "Low (30)", "Medium (60)", "High (90)", "Back"
        or just set self.config["oled_brightness"].
        """
        self.logger.info("ConfigMenu: Opening contrast sub-menu... (not implemented here)")
        # For demonstration, let's just set a brightness to 50:
        self.mode_manager.config["oled_brightness"] = 50
        # Save the preference:
        self.mode_manager.save_preferences()
        # Then return to config menu or clock:
        self.logger.info("Brightness set to 50. Returning to clock.")
        self.stop_mode()
        self.mode_manager.to_clock()
