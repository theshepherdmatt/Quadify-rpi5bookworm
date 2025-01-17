import logging
import time
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class DisplayMenu(BaseManager):
    """
    A scrollable menu using 'anchored scrolling' (like RadioManager).

    Main Menu Items:
      1) Display Modes
      2) Spectrum
      3) Brightness
      4) Back  (-> returns to Config Menu)

    Sub-menus (no "Back" line):
      - Display Modes: ["Modern", "Original", "Minimal", "System Info"]
      - Spectrum:      ["Off", "On"]
      - Brightness:    ["Low", "Medium", "High"]

    Selecting an item in a sub-menu applies the change, then automatically
    returns to the main menu. The only 'Back' line is in the main menu,
    which calls `self.stop_mode()` and `to_configmenu()`.
    """

    def __init__(
        self,
        display_manager,
        mode_manager,
        window_size=4,     # Number of lines visible at once
        y_offset=2,
        line_spacing=15
    ):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.is_active = False
        self.current_menu = "main"  # Could be: "main", "display_modes", "spectrum", or "brightness"

        # Debounce
        self.last_action_time = 0
        self.debounce_interval = 0.3

        # Layout / scrolling
        self.window_size = window_size
        self.window_start_index = 0
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Font
        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        # MAIN menu items
        self.main_items = [
            "Display Modes",
            "Spectrum",
            "Brightness",
            "Back"
        ]

        # SUB-menu items (no 'Back' lines here)
        self.display_modes_items = ["Modern", "Original", "Minimal", "System Info"]
        self.spectrum_items      = ["Off", "On"]
        self.brightness_items    = ["Low", "Medium", "High"]

        # We'll store whichever list is active in `self.current_list`
        self.current_list = self.main_items

        # Current selection index
        self.current_selection_index = 0

    # ----------------------------------------------------------------
    # Start / Stop
    # ----------------------------------------------------------------
    def start_mode(self):
        """Activate and display the main menu."""
        if self.is_active:
            self.logger.debug("DisplayMenu: Already active.")
            return
        self.is_active = True
        self.logger.info("DisplayMenu: Starting display menu.")

        self.current_menu = "main"
        self.current_list = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self._display_current_menu()

    def stop_mode(self):
        """Stop the menu and clear the display."""
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("DisplayMenu: Stopped and cleared display.")

    # ----------------------------------------------------------------
    # Scroll & Select
    # ----------------------------------------------------------------
    def scroll_selection(self, direction):
        """
        Update current_selection_index, re-display the appropriate menu,
        with anchor logic so the highlighted row remains near center.
        """
        if not self.is_active:
            self.logger.warning("DisplayMenu: Scroll attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("DisplayMenu: Scroll debounced.")
            return
        self.last_action_time = now

        old_index = self.current_selection_index
        list_length = len(self.current_list)

        # Move selection up/down
        if direction > 0 and self.current_selection_index < list_length - 1:
            self.current_selection_index += 1
        elif direction < 0 and self.current_selection_index > 0:
            self.current_selection_index -= 1

        if self.current_selection_index != old_index:
            self.logger.debug(
                f"DisplayMenu: Scrolled from {old_index} to {self.current_selection_index}"
            )
            self._display_current_menu()

    def select_item(self):
        """Handle selection in the current menu (main or sub)."""
        if not self.is_active:
            self.logger.warning("DisplayMenu: Select attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("DisplayMenu: Select debounced.")
            return
        self.last_action_time = now

        selected_item = self.current_list[self.current_selection_index]
        self.logger.info(
            f"DisplayMenu: Selected => {selected_item} in menu '{self.current_menu}'"
        )

        # MAIN menu logic
        if self.current_menu == "main":
            if selected_item == "Display Modes":
                self.current_menu = "display_modes"
                self.current_list = self.display_modes_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._display_current_menu()

            elif selected_item == "Spectrum":
                self.current_menu = "spectrum"
                self.current_list = self.spectrum_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._display_current_menu()

            elif selected_item == "Brightness":
                self.current_menu = "brightness"
                self.current_list = self.brightness_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._display_current_menu()

            elif selected_item == "Back":
                # Return to config menu
                self.stop_mode()
                self.mode_manager.to_configmenu()
            else:
                self.logger.warning(f"DisplayMenu: Unknown main item => {selected_item}")

        # DISPLAY MODES sub-menu
        elif self.current_menu == "display_modes":
            # No "Back" item here, so any selection just applies and returns to main
            self._handle_display_mode(selected_item)

            # After applying, go back to main
            self.current_menu = "main"
            self.current_list = self.main_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self._display_current_menu()

        # SPECTRUM sub-menu
        elif self.current_menu == "spectrum":
            # No "Back" item here either
            self._handle_spectrum(selected_item)

            # Return to main
            self.current_menu = "main"
            self.current_list = self.main_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self._display_current_menu()

        # BRIGHTNESS sub-menu
        elif self.current_menu == "brightness":
            # No "Back" item here
            self._handle_brightness(selected_item)

            self.current_menu = "main"
            self.current_list = self.main_items
            self.current_selection_index = 0
            self.window_start_index = 0
            self._display_current_menu()

        else:
            self.logger.warning(f"DisplayMenu: Unrecognized sub-menu => {self.current_menu}")

    # ----------------------------------------------------------------
    # Display the current menu (main or sub)
    # ----------------------------------------------------------------
    def _display_current_menu(self):
        """Draw the current list with anchored scrolling logic."""
        if not self.is_active:
            return

        visible_items = self._get_visible_window(self.current_list, self.current_selection_index)

        def draw(draw_obj):
            for i, item_name in enumerate(visible_items):
                actual_index = self.window_start_index + i
                is_selected = (actual_index == self.current_selection_index)

                # If selected is "Back" in main menu, show "<- "; otherwise "-> "
                if self.current_menu == "main" and is_selected and item_name == "Back":
                    arrow = "<- "
                elif is_selected:
                    arrow = "-> "
                else:
                    arrow = "   "

                fill_color = "white" if is_selected else "gray"
                y_pos = self.y_offset + i * self.line_spacing

                draw_obj.text(
                    (5, y_pos),
                    f"{arrow}{item_name}",
                    font=self.font,
                    fill=fill_color
                )

        self.display_manager.draw_custom(draw)
        self.logger.debug(
            f"DisplayMenu: {self.current_menu} => {self.current_list}, "
            f"index={self.current_selection_index}, window_start={self.window_start_index}"
        )

    def _get_visible_window(self, items, selected_index):
        """
        Use the same anchored approach as RadioManager:
        Keep the selected item in the middle unless near edges.
        """
        total_items = len(items)
        half_window = self.window_size // 2

        # Attempt to center the selection
        tentative_start = selected_index - half_window

        if tentative_start < 0:
            self.window_start_index = 0
        elif tentative_start + self.window_size > total_items:
            self.window_start_index = max(total_items - self.window_size, 0)
        else:
            self.window_start_index = tentative_start

        end_index = self.window_start_index + self.window_size
        visible_slice = items[self.window_start_index:end_index]

        self.logger.debug(
            f"DisplayMenu: Window => start={self.window_start_index}, "
            f"size={self.window_size}, selection={selected_index}, total={total_items}"
        )
        return visible_slice

    # ----------------------------------------------------------------
    # Actions for Display Modes, Spectrum, Brightness
    # ----------------------------------------------------------------
    def _handle_display_mode(self, mode_name):
        """
        "Modern" => set display_mode to "modern"
        "Original" => "original"
        "Minimal" => "minimal"
        "System Info" => "systeminfo"
        """
        display_map = {
            "Modern": "modern",
            "Original": "original",
            "Minimal": "minimal",
            "System Info": "systeminfo",
        }
        mapped = display_map.get(mode_name)
        if mapped:
            self.logger.info(f"DisplayMenu: Setting display mode => {mapped}")
            self.mode_manager.set_display_mode(mapped)
        else:
            self.logger.warning(f"DisplayMenu: Unknown display mode => {mode_name}")

    def _handle_spectrum(self, option):
        """
        "Off" => self.mode_manager.config["cava_enabled"] = False
        "On"  => self.mode_manager.config["cava_enabled"] = True
        """
        if option == "Off":
            self.mode_manager.config["cava_enabled"] = False
            self.logger.info("DisplayMenu: Spectrum => Off")
        elif option == "On":
            self.mode_manager.config["cava_enabled"] = True
            self.logger.info("DisplayMenu: Spectrum => On")
        else:
            self.logger.warning(f"DisplayMenu: Unknown spectrum option => {option}")

        self.mode_manager.save_preferences()

    def _handle_brightness(self, level):
        """
        "Low" => contrast(50)
        "Medium" => contrast(150)
        "High" => contrast(255)
        """
        brightness_map = {
            "Low": 50,
            "Medium": 150,
            "High": 255
        }
        val = brightness_map.get(level)
        if val is not None:
            # Attempt to call .contrast() if available
            if hasattr(self.display_manager.oled, "contrast"):
                try:
                    self.display_manager.oled.contrast(val)
                    self.logger.info(f"DisplayMenu: Brightness => {level} ({val})")
                except Exception as e:
                    self.logger.error(f"DisplayMenu: Failed to set brightness => {e}")
            else:
                self.logger.warning("DisplayMenu: .contrast() not available on this device.")

            # Save in config
            self.mode_manager.config["oled_brightness"] = val
            self.mode_manager.save_preferences()
        else:
            self.logger.warning(f"DisplayMenu: Unknown brightness => {level}")
