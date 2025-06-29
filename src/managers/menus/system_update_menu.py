import logging
import time
import subprocess
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class SystemUpdateMenu(BaseManager):
    """
    A scrollable menu for handling "System Update" interactions:
      - Main menu:
         1) "Update from GitHub"
         2) "Back"
      - Confirm sub-menu:
         1) "Yes"
         2) "No"
    """

    def __init__(
        self,
        display_manager,
        mode_manager,
        window_size=4,
        y_offset=2,
        line_spacing=15
    ):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.is_active = False
        self.current_menu = "main"

        self.last_action_time = 0
        self.debounce_interval = 0.3

        self.window_size = window_size
        self.window_start_index = 0
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        self.main_items = ["Update from GitHub", "Back"]
        self.confirm_items = ["Yes", "No"]

        self.current_list = self.main_items
        self.current_selection_index = 0

    def start_mode(self):
        if self.is_active:
            self.logger.debug("SystemUpdateMenu: Already active.")
            return

        self.is_active = True
        self.logger.info("SystemUpdateMenu: Starting system update menu.")

        self.current_menu = "main"
        self.current_list = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self._display_current_menu()

    def stop_mode(self):
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("SystemUpdateMenu: Stopped and cleared display.")

    def scroll_selection(self, direction):
        if not self.is_active:
            self.logger.warning("SystemUpdateMenu: Scroll attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("SystemUpdateMenu: Scroll debounced.")
            return
        self.last_action_time = now

        old_index = self.current_selection_index
        list_length = len(self.current_list)

        if direction > 0 and self.current_selection_index < list_length - 1:
            self.current_selection_index += 1
        elif direction < 0 and self.current_selection_index > 0:
            self.current_selection_index -= 1

        if self.current_selection_index != old_index:
            self.logger.debug(f"SystemUpdateMenu: Scrolled from {old_index} to {self.current_selection_index}")
            self._display_current_menu()

    def select_item(self):
        if not self.is_active:
            self.logger.warning("SystemUpdateMenu: Select attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("SystemUpdateMenu: Select debounced.")
            return
        self.last_action_time = now

        selected_item = self.current_list[self.current_selection_index]
        self.logger.info(f"SystemUpdateMenu: Selected => {selected_item} in menu '{self.current_menu}'")

        if self.current_menu == "main":
            if selected_item == "Update from GitHub":
                self.current_menu = "confirm"
                self.current_list = self.confirm_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._display_current_menu()

            elif selected_item == "Back":
                self.stop_mode()
                self.mode_manager.back()

            else:
                self.logger.warning(f"SystemUpdateMenu: Unknown main item => {selected_item}")

        elif self.current_menu == "confirm":
            if selected_item == "Yes":
                self.display_manager.clear_screen()

                def draw(draw_obj):
                    text = "Updating from GitHub\nRestarting services..."
                    draw_obj.text((10, 20), text, font=self.font, fill="white")

                self.display_manager.draw_custom(draw)
                self.logger.info("SystemUpdateMenu: Displayed update message.")
                time.sleep(5)
                self.stop_mode()

                self.logger.info("SystemUpdateMenu: Running update script.")
                subprocess.call(["bash", "/home/volumio/Quadify/scripts/quadify_autoupdate.sh"])

            else:
                self.current_menu = "main"
                self.current_list = self.main_items
                self.current_selection_index = 0
                self.window_start_index = 0
                self._display_current_menu()

        else:
            self.logger.warning(f"SystemUpdateMenu: Unrecognized menu => {self.current_menu}")

    def _display_current_menu(self):
        if not self.is_active:
            return

        visible_items = self._get_visible_window(self.current_list, self.current_selection_index)

        def draw(draw_obj):
            for i, item_name in enumerate(visible_items):
                actual_index = self.window_start_index + i
                is_selected = (actual_index == self.current_selection_index)

                arrow = "-> " if is_selected else "   "
                fill_color = "white" if is_selected else "gray"
                y_pos = self.y_offset + i * self.line_spacing

                draw_obj.text(
                    (5, y_pos),
                    f"{arrow}{item_name}",
                    font=self.font,
                    fill=fill_color
                )

        self.display_manager.draw_custom(draw)

    def _get_visible_window(self, items, selected_index):
        total_items = len(items)
        half_window = self.window_size // 2

        tentative_start = selected_index - half_window

        if tentative_start < 0:
            self.window_start_index = 0
        elif tentative_start + self.window_size > total_items:
            self.window_start_index = max(total_items - self.window_size, 0)
        else:
            self.window_start_index = tentative_start

        end_index = self.window_start_index + self.window_size
        return items[self.window_start_index:end_index]

    def back(self):
        if self.is_active:
            self.stop_mode()
        self.mode_manager.back()
