import logging
import time
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class ConfigMenu(BaseManager):
    """
    A text-list menu for configuration items, ending with "Back".
    When "Back" is selected, it shows a left arrow "<- ".
    For all other selected items, show "-> ".
    Scrolling is handled simply: we move the selection up or down,
    then adjust a window slice if needed.
    """

    def __init__(
        self,
        display_manager,
        mode_manager,
        window_size=5,
        y_offset=2,
        line_spacing=15
    ):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Menu state
        self.is_active = False
        self.current_index = 0
        self.window_start_index = 0
        self.window_size = window_size
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Debounce
        self.last_action_time = 0
        self.debounce_interval = 0.3

        # Font
        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        # Menu items
        self.menu_items = [
            "Display Settings",
            "Clock Settings",
            "Screensaver Settings",
            "Back"
        ]

    def start_mode(self):
        """Activate the config menu and draw the items."""
        if self.is_active:
            self.logger.debug("ConfigMenu: already active.")
            return
        self.is_active = True
        self.logger.info("ConfigMenu: Starting config menu.")
        self.display_items()

    def stop_mode(self):
        """Deactivate and clear the display."""
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("ConfigMenu: Stopped and cleared display.")

    def display_items(self):
        """
        Show the currently visible slice of items.
        Selected item shows "-> " unless it's "Back", which shows "<- ".
        """
        # Calculate which items are visible
        end_index = self.window_start_index + self.window_size
        visible_items = self.menu_items[self.window_start_index:end_index]

        def draw(draw_obj):
            for i, item_name in enumerate(visible_items):
                actual_index = self.window_start_index + i
                selected = (actual_index == self.current_index)

                if selected:
                    arrow = "<- " if item_name == "Back" else "-> "
                    fill_color = "white"
                else:
                    arrow = "   "
                    fill_color = "gray"

                y_pos = self.y_offset + i * self.line_spacing
                draw_obj.text(
                    (5, y_pos),
                    f"{arrow}{item_name}",
                    font=self.font,
                    fill=fill_color
                )

        self.display_manager.draw_custom(draw)
        self.logger.debug(
            f"ConfigMenu: Displayed items {self.window_start_index} "
            f"to {end_index - 1}, selected={self.current_index}"
        )

    def scroll_selection(self, direction):
        """Move the selection by 'direction' (+1 or -1) and redraw."""
        if not self.is_active:
            self.logger.warning("ConfigMenu: Attempted scroll while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            return
        self.last_action_time = now

        old_index = self.current_index
        self.current_index += direction
        # Clamp between 0 and last index
        self.current_index = max(0, min(self.current_index, len(self.menu_items) - 1))

        # Adjust window_start_index if we scroll past current window
        if self.current_index < self.window_start_index:
            self.window_start_index = self.current_index
        elif self.current_index >= self.window_start_index + self.window_size:
            self.window_start_index = self.current_index - self.window_size + 1

        if old_index != self.current_index:
            self.logger.debug(
                f"ConfigMenu: Scrolled from {old_index} to {self.current_index}, "
                f"window_start_index={self.window_start_index}"
            )
            self.display_items()

    def select_item(self):
        """Perform the action for the currently selected menu item."""
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
            self.stop_mode()
            self.mode_manager.to_displaymenu()
        elif selected == "Clock Settings":
            self.stop_mode()
            self.mode_manager.to_clockmenu()
        elif selected == "Screensaver Settings":
            self.stop_mode()
            self.mode_manager.to_screensavermenu()
        elif selected == "Back":
            self.stop_mode()
            self.mode_manager.to_menu()  # Or wherever "Back" should lead
        else:
            self.logger.warning(f"Unrecognized config option: {selected}")
