import logging
import time
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class ClockMenu(BaseManager):
    """
    A scrollable 'Clock' settings menu:

      Main Menu:
        1) Show Seconds  -> Sub-menu: [On, Off]
        2) Show Date     -> Sub-menu: [On, Off]
        3) Select Font   -> Sub-menu: [Sans, Dots, Digital, Bold, Back]
        4) Back          -> returns to Display Menu

      The On/Off sub-menus have no 'Back' item; selecting On or Off
      updates the config and returns you to the main clock menu.
      The Font sub-menu has 'Back' to let you exit without changing.
    """

    def __init__(
        self,
        display_manager,
        mode_manager,
        window_size=4,  # number of lines visible
        y_offset=2,
        line_spacing=15
    ):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Menu states
        self.is_active = False
        self.current_menu = "main"  # "main", "seconds", "date", or "fonts"

        # Debounce
        self.last_action_time = 0
        self.debounce_interval = 0.3

        # Layout
        self.window_size = window_size
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Font
        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        # Main menu
        self.main_items = [
            "Show Seconds",
            "Show Date",
            "Select Font",
            "Back"  # => return to Display Menu
        ]

        # Sub-menus
        # No 'Back' for Show Seconds or Show Date => On/Off only
        self.seconds_items = ["On", "Off"]
        self.date_items = ["On", "Off"]

        # Font sub-menu does include 'Back'
        self.font_items = ["Sans", "Dots", "Digital", "Bold", "Back"]

        # Current data
        self.current_items = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0

    # ----------------------------------------------------------------
    # Start / Stop
    # ----------------------------------------------------------------
    def start_mode(self):
        """Activate the clock menu and display the main items."""
        if self.is_active:
            self.logger.debug("ClockMenu: Already active.")
            return
        self.is_active = True
        self.logger.info("ClockMenu: Starting clock menu.")

        self.current_menu = "main"
        self.current_items = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self._draw_current_menu()

    def stop_mode(self):
        """Deactivate and clear the display."""
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("ClockMenu: Stopped clock menu.")

    # ----------------------------------------------------------------
    # Scrolling
    # ----------------------------------------------------------------
    def scroll_selection(self, direction):
        """
        Anchored scrolling: the highlight stays near the middle row
        until reaching top/bottom.
        """
        if not self.is_active:
            self.logger.warning("ClockMenu: Scroll attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("ClockMenu: Scroll debounced.")
            return
        self.last_action_time = now

        old_index = self.current_selection_index
        total_items = len(self.current_items)

        # Move up/down
        if direction > 0 and self.current_selection_index < total_items - 1:
            self.current_selection_index += 1
        elif direction < 0 and self.current_selection_index > 0:
            self.current_selection_index -= 1

        if self.current_selection_index != old_index:
            self.logger.debug(f"ClockMenu: Scrolled from {old_index} to {self.current_selection_index}")
            self._draw_current_menu()

    # ----------------------------------------------------------------
    # Selection
    # ----------------------------------------------------------------
    def select_item(self):
        """
        Main menu => 'Show Seconds', 'Show Date', 'Select Font', 'Back'.
        Sub-menus => On/Off or Font choices.
        """
        if not self.is_active:
            self.logger.warning("ClockMenu: Select attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("ClockMenu: Select debounced.")
            return
        self.last_action_time = now

        selected = self.current_items[self.current_selection_index]
        self.logger.info(f"ClockMenu: Selected => {selected} (menu={self.current_menu})")

        # MAIN menu
        if self.current_menu == "main":
            if selected == "Show Seconds":
                # Go to the On/Off sub-menu
                self.current_menu = "seconds"
                self.current_items = self.seconds_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._draw_current_menu()

            elif selected == "Show Date":
                # On/Off sub-menu
                self.current_menu = "date"
                self.current_items = self.date_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._draw_current_menu()

            elif selected == "Select Font":
                self.current_menu = "fonts"
                self.current_items = self.font_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._draw_current_menu()

            elif selected == "Back":
                # Return to Display Menu
                self.logger.info("ClockMenu: 'Back' => to Display Menu")
                self.stop_mode()
                self.mode_manager.to_displaymenu()

            else:
                self.logger.warning(f"ClockMenu: Unknown main item => {selected}")

        # SUB-MENU: Show Seconds => ["On", "Off"]
        elif self.current_menu == "seconds":
            if selected == "On":
                self.logger.info("ClockMenu: 'Show Seconds' => On")
                self.mode_manager.config["show_seconds"] = True
                self.mode_manager.save_preferences()
            elif selected == "Off":
                self.logger.info("ClockMenu: 'Show Seconds' => Off")
                self.mode_manager.config["show_seconds"] = False
                self.mode_manager.save_preferences()
            else:
                self.logger.warning(f"ClockMenu: Unknown item => {selected}")

            # After selection, go back to main clock menu
            self._return_to_main()

        # SUB-MENU: Show Date => ["On", "Off"]
        elif self.current_menu == "date":
            if selected == "On":
                self.logger.info("ClockMenu: 'Show Date' => On")
                self.mode_manager.config["show_date"] = True
                self.mode_manager.save_preferences()
            elif selected == "Off":
                self.logger.info("ClockMenu: 'Show Date' => Off")
                self.mode_manager.config["show_date"] = False
                self.mode_manager.save_preferences()
            else:
                self.logger.warning(f"ClockMenu: Unknown item => {selected}")

            self._return_to_main()

        # SUB-MENU: Fonts => ["Sans", "Dots", "Digital", "Bold", "Back"]
        elif self.current_menu == "fonts":
            if selected == "Back":
                self._return_to_main()
            else:
                self._handle_font_selection(selected)
                self._return_to_main()

        else:
            self.logger.warning(f"ClockMenu: Unknown current_menu => {self.current_menu}")

    # ----------------------------------------------------------------
    # Return to main
    # ----------------------------------------------------------------
    def _return_to_main(self):
        """Go back to the main clock menu from any sub-menu."""
        self.current_menu = "main"
        self.current_items = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self._draw_current_menu()

    # ----------------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------------
    def _draw_current_menu(self):
        """Draw the current list with the anchored window approach."""
        if not self.is_active:
            return

        visible_slice = self._get_visible_slice(self.current_items)

        def draw(draw_obj):
            for i, item_name in enumerate(visible_slice):
                actual_index = self.window_start_index + i
                is_selected = (actual_index == self.current_selection_index)

                # Show "<- " if selected and item is "Back"
                if is_selected and item_name == "Back":
                    arrow = "<- "
                elif is_selected:
                    arrow = "-> "
                else:
                    arrow = "   "

                fill_color = "white" if is_selected else "gray"
                y_pos = self.y_offset + i * self.line_spacing
                draw_obj.text((5, y_pos), f"{arrow}{item_name}", font=self.font, fill=fill_color)

        self.display_manager.draw_custom(draw)
        self.logger.debug(
            f"ClockMenu: current_menu={self.current_menu}, "
            f"items={self.current_items}, "
            f"index={self.current_selection_index}, window_start={self.window_start_index}"
        )

    def _get_visible_slice(self, items):
        """
        Keep the selection near the middle if possible.
        """
        total = len(items)
        half_window = self.window_size // 2

        tentative_start = self.current_selection_index - half_window

        if tentative_start < 0:
            self.window_start_index = 0
        elif tentative_start + self.window_size > total:
            self.window_start_index = max(total - self.window_size, 0)
        else:
            self.window_start_index = tentative_start

        end_index = self.window_start_index + self.window_size
        return items[self.window_start_index:end_index]

    # ----------------------------------------------------------------
    # Font Setting
    # ----------------------------------------------------------------
    def _handle_font_selection(self, selected):
        """
        E.g. "Sans" => 'clock_sans', "Dots" => 'clock_dots', "Digital" => 'clock_digital'.
        """
        mapping = {
            "Sans": "clock_sans",
            "Dots": "clock_dots",
            "Digital": "clock_digital",
            "Bold": "clock_bold"
        }
        chosen = mapping.get(selected)
        if chosen:
            self.mode_manager.config["clock_font_key"] = chosen
            self.logger.info(f"ClockMenu: Set font => {chosen}")
            self.mode_manager.save_preferences()
        else:
            self.logger.warning(f"ClockMenu: Unknown font => {selected}")
