# src/managers/menus/screensaver_menu.py

from managers.menus.base_manager import BaseManager
import logging
from PIL import ImageFont
import time

class ScreensaverMenu(BaseManager):
    """
    A text-list menu for picking which screensaver to use at idle,
    plus a sub-menu for adjusting the screensaver timeout.
    """

    def __init__(
        self,
        display_manager,
        mode_manager,
        window_size=5,    
        y_offset=1,
        line_spacing=12
    ):
        super().__init__(display_manager, None, mode_manager)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

        self.mode_manager = mode_manager
        self.display_manager = display_manager
        self.is_active = False

        # Font for text drawing
        self.font_key = "menu_font"
        self.font = self.display_manager.fonts.get(self.font_key) or ImageFont.load_default()

        # Main screensaver items (added "Timer")
        self.screensaver_items = ["None", "Snake", "Stars", "Quadify", "Timer"]
        self.current_index = 0

        # A separate list for timer values (in seconds).
        # We'll display them as text like "1 min", "2 min", etc.
        # (1 minute = 60, 2 min = 120, 5 min = 300, 10 min=600, 1 hour=3600)
        self.timer_items = [
            ("1 min",   60),
            ("2 min",   120),
            ("5 min",   300),
            ("10 min",  600),
            ("1 hour",  3600),
        ]
        self.submenu_active = False
        self.current_submenu_name = None

        # Layout
        self.window_size = window_size
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Debounce
        self.last_action_time = 0
        self.debounce_interval = 0.3

        # Save a stack if you want to go back
        self.menu_stack = []

    # -------------------------------------------------------
    # Activation / Deactivation
    # -------------------------------------------------------
    def start_mode(self):
        if self.is_active:
            self.logger.debug("ScreensaverMenu: Already active.")
            return
        self.is_active = True
        self.logger.info("ScreensaverMenu: Starting screensaver selection menu.")

        # We start on the main list
        self.submenu_active = False
        self.current_submenu_name = None
        self._show_main_list()

    def stop_mode(self):
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("ScreensaverMenu: Stopped and cleared display.")

    # -------------------------------------------------------
    # Display
    # -------------------------------------------------------
    def _show_main_list(self):
        """Show the main list of screensaver items + 'Timer'."""
        self._draw_items(self.screensaver_items, self.current_index)

    def _show_timer_list(self):
        """Show the sub-menu for picking a screensaver timeout."""
        # We'll treat self.timer_items as the options
        # current_index is used for them too
        labels = [pair[0] for pair in self.timer_items]
        self._draw_items(labels, self.current_index)

    def _draw_items(self, items, highlight_index):
        def draw(draw_obj):
            for i, name in enumerate(items):
                arrow = "-> " if i == highlight_index else "   "
                fill_color = "white" if i == highlight_index else "gray"
                y_pos = self.y_offset + i * self.line_spacing
                draw_obj.text((5, y_pos), f"{arrow}{name}", font=self.font, fill=fill_color)

        self.display_manager.draw_custom(draw)

    # -------------------------------------------------------
    # Scrolling & Selection
    # -------------------------------------------------------
    def scroll_selection(self, direction):
        if not self.is_active:
            self.logger.warning("ScreensaverMenu: Attempted scroll while inactive.")
            return
        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("ScreensaverMenu: Scroll debounced.")
            return
        self.last_action_time = now

        old_index = self.current_index
        # If in sub-menu (timer), we scroll within self.timer_items
        if self.submenu_active and self.current_submenu_name == "timer":
            max_index = len(self.timer_items) - 1
        else:
            max_index = len(self.screensaver_items) - 1

        self.current_index += direction
        self.current_index = max(0, min(self.current_index, max_index))

        if old_index != self.current_index:
            self.logger.debug(f"ScreensaverMenu: scrolled from {old_index} to {self.current_index}")
            if self.submenu_active and self.current_submenu_name == "timer":
                self._show_timer_list()
            else:
                self._show_main_list()

    def select_item(self):
        if not self.is_active:
            self.logger.warning("ScreensaverMenu: Attempted select while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("ScreensaverMenu: Select debounced.")
            return
        self.last_action_time = now

        if self.submenu_active and self.current_submenu_name == "timer":
            # We are picking a screensaver timeout
            self._handle_timer_selection()
            return
        else:
            # We are on the main list
            selected_name = self.screensaver_items[self.current_index]
            self.logger.info(f"ScreensaverMenu: Selected => {selected_name}")

            if selected_name == "None":
                self.mode_manager.config["screensaver_type"] = "none"
                self._save_and_return_to_clock()

            elif selected_name == "Snake":
                self.mode_manager.config["screensaver_type"] = "snake"
                self._save_and_return_to_clock()

            elif selected_name == "Stars":
                self.mode_manager.config["screensaver_type"] = "stars"
                self._save_and_return_to_clock()

            elif selected_name == "Quadify":
                self.mode_manager.config["screensaver_type"] = "quadify"
                self._save_and_return_to_clock()

            elif selected_name == "Timer":
                # Open sub-menu to pick the screensaver timeout
                self._open_timer_submenu()
            else:
                self.logger.warning(f"ScreensaverMenu: Unrecognized option: {selected_name}")
                self.mode_manager.config["screensaver_type"] = "none"
                self._save_and_return_to_clock()

    # -------------------------------------------------------
    # Timer Sub-Menu Logic
    # -------------------------------------------------------
    def _open_timer_submenu(self):
        """Switch from the main list to a sub-menu of possible timeouts."""
        self.submenu_active = True
        self.current_submenu_name = "timer"

        # Save current_index in case we want to go back
        self.menu_stack.append((self.screensaver_items, self.current_index))

        self.current_index = 0  # start at top of the timer list
        self._show_timer_list()

    def _handle_timer_selection(self):
        """User picked an item from the timer sub-menu."""
        label, seconds = self.timer_items[self.current_index]
        self.logger.info(f"ScreensaverMenu: Timer selection => {label} = {seconds} seconds")

        # Store it in mode_manager.config
        self.mode_manager.config["screensaver_timeout"] = seconds
        self.mode_manager.save_preferences()
        self.logger.debug(f"ScreensaverMenu: config['screensaver_timeout'] = {seconds} now stored.")

        # Return to main list or exit
        # We'll demonstrate returning to main list
        self.submenu_active = False
        self.current_submenu_name = None
        self.current_index = 0

        # If you want to restore the old position in the main list, do:
        if self.menu_stack:
            old_items, old_index = self.menu_stack.pop()
            # old_items should be self.screensaver_items
            # but we only have 1 sub-menu, so no need to store them again
            self.current_index = old_index

        # Show the main list again
        self.stop_mode()
        self.mode_manager.to_clock()

    # -------------------------------------------------------
    # Helper to store and revert to clock
    # -------------------------------------------------------
    def _save_and_return_to_clock(self):
        self.mode_manager.save_preferences()
        self.logger.debug(f"ScreensaverMenu: config['screensaver_type'] is now {self.mode_manager.config['screensaver_type']}")
        self.logger.debug("ScreensaverMenu: Returning to clock after selection.")
        self.stop_mode()
        self.mode_manager.to_clock()
