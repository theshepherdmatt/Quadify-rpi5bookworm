import logging
import time
import os
import subprocess
from PIL import ImageFont
from managers.menus.base_manager import BaseManager
import sys

class RemoteMenu(BaseManager):
    """
    A scrollable menu for selecting and installing an IR remote configuration.
    
    Each remote configuration is stored in a folder under:
      /home/volumio/Quadify/lirc/configurations/
      
    For example, the "Apple Remote A1156" folder should contain:
      - lircd.conf
      - lircrc
      
    When a remote is selected, a privileged helper is invoked to install the configuration:
      - Copies files to /etc/lirc/lircd.conf (for the IR codes)
      - Copies files to /etc/lirc/lircrc (for the client mapping)
      - Restarts the LIRC daemon and the ir_listener service
      - (After displaying a message on the OLED, waits 10 seconds before rebooting)
    """
    
    def __init__(self, display_manager, mode_manager, window_size=4, y_offset=2, line_spacing=15):
        super().__init__(display_manager, None, mode_manager)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_active = False

        # Debounce settings
        self.last_action_time = 0
        self.debounce_interval = 0.3

        # Layout / scrolling
        self.window_size = window_size
        self.window_start_index = 0
        self.y_offset = y_offset
        self.line_spacing = line_spacing

        # Font for the menu
        self.font_key = "menu_font"
        self.font = display_manager.fonts.get(self.font_key, ImageFont.load_default())

        # Define the remote configuration options (folder names).
        self.remote_options = [
            "Apple Remote A1156",
            "Apple Remote A1156 Alternative",
            "Apple Remote A1294",
            "Apple Remote A1294 Alternative",
            "Arcam ir-DAC-II Remote",
            "Atrix Remote",
            "Bluesound RC1",
            "Denon Remote RC-1204",
            "JustBoom IR Remote",
            "Marantz RC003PMCD",
            "Odroid Remote",
            "Philips CD723",
            "PDP Gaming Remote Control",
            "Samsung AA59-00431A",
            "Samsung_BN59-006XXA",
            "XBox 360 Remote",
            "XBox One Remote",
            "Xiaomi IR for TV box",
            "Yamaha RAV363"
        ]
        
        # Append a "Back" option to allow the user to exit.
        self.current_list = self.remote_options + ["Back"]
        self.current_selection_index = 0

    # ----------------------------------------------------------------
    # Start / Stop Methods
    # ----------------------------------------------------------------
    def start_mode(self):
        """Activate and display the remote configuration menu."""
        if self.is_active:
            self.logger.debug("RemoteMenu: Already active.")
            return
        self.is_active = True
        self.logger.info("RemoteMenu: Starting remote configuration menu.")
        self.current_selection_index = 0
        self.window_start_index = 0
        self._display_current_menu()

    def stop_mode(self):
        """Stop the menu and clear the display."""
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("RemoteMenu: Stopped and cleared display.")

    # ----------------------------------------------------------------
    # Scroll & Select Methods
    # ----------------------------------------------------------------
    def scroll_selection(self, direction):
        """
        Update the current_selection_index based on the direction.
        """
        if not self.is_active:
            self.logger.warning("RemoteMenu: Scroll attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("RemoteMenu: Scroll debounced.")
            return
        self.last_action_time = now

        old_index = self.current_selection_index
        list_length = len(self.current_list)

        if direction > 0 and self.current_selection_index < list_length - 1:
            self.current_selection_index += 1
        elif direction < 0 and self.current_selection_index > 0:
            self.current_selection_index -= 1

        if self.current_selection_index != old_index:
            self.logger.debug(
                f"RemoteMenu: Scrolled from {old_index} to {self.current_selection_index}"
            )
            self._display_current_menu()

    def select_item(self):
        """Handle selection in the remote configuration menu."""
        if not self.is_active:
            self.logger.warning("RemoteMenu: Select attempted while inactive.")
            return

        now = time.time()
        if now - self.last_action_time < self.debounce_interval:
            self.logger.debug("RemoteMenu: Select debounced.")
            return
        self.last_action_time = now

        selected_item = self.current_list[self.current_selection_index]
        self.logger.info(f"RemoteMenu: Selected => {selected_item}")

        if selected_item == "Back":
            # Go back to the previous menu
            self.stop_mode()
            self.mode_manager.back()
        else:
            # Define the source directory.
            source_dir = f"/home/volumio/Quadify/lirc/configurations/{selected_item}"
            if os.path.isdir(source_dir):
                try:
                    # First, display a message on the OLED screen
                    self.display_manager.clear_screen()
                    def draw_msg(draw_obj):
                        draw_obj.text((10, 20), "IR remote selected,\nrebooting in 10 seconds...", font=self.font, fill="white")
                    self.display_manager.draw_custom(draw_msg)
                    time.sleep(10)
                    
                    # Now call the privileged helper to install the configuration.
                    # Replace '/home/volumio/Quadify/run_remote_config' with your helper's path.
                    result = subprocess.call(["/home/volumio/Quadify/scripts/install_remote_config.sh", selected_item])
                    if result == 0:
                        self.logger.info(f"RemoteMenu: Installed configuration for '{selected_item}'.")
                        self.stop_mode()
                        self.mode_manager.to_configmenu()
                    else:
                        self.logger.error(f"RemoteMenu: Error installing configuration, helper returned {result}")

                        self.display_manager.clear_screen()
                        def draw_err(draw_obj):
                            draw_obj.text((10, 20), "Installation Error!", font=self.font, fill="white")
                        self.display_manager.draw_custom(draw_err)
                        time.sleep(2)
                        self._display_current_menu()
                except Exception as e:
                    self.logger.error(f"RemoteMenu: Exception during installation: {e}")
                    self.display_manager.clear_screen()
                    def draw_exc(draw_obj):
                        draw_obj.text((10, 20), "Installation Error!", font=self.font, fill="white")
                    self.display_manager.draw_custom(draw_exc)
                    time.sleep(2)
                    self._display_current_menu()
            else:
                self.logger.error(f"RemoteMenu: Folder not found: {source_dir}")
                self.display_manager.clear_screen()
                def draw_not_found(draw_obj):
                    draw_obj.text((10, 20), "Config folder not found!", font=self.font, fill="white")
                self.display_manager.draw_custom(draw_not_found)
                time.sleep(2)
                self._display_current_menu()

    # ----------------------------------------------------------------
    # Display Methods
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
                arrow = "-> " if is_selected else "   "
                fill_color = "white" if is_selected else "gray"
                y_pos = self.y_offset + i * self.line_spacing
                draw_obj.text((5, y_pos), f"{arrow}{item_name}", font=self.font, fill=fill_color)

        self.display_manager.draw_custom(draw)

    def _get_visible_window(self, items, selected_index):
        """
        Use an anchored scrolling approach to keep the selected item centred.
        """
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

