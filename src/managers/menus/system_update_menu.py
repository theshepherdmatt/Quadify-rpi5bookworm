import logging
import time
import subprocess
from pathlib import Path
from PIL import ImageFont
from managers.menus.base_manager import BaseManager


class SystemUpdateMenu(BaseManager):
    """
    A scrollable menu for handling Quadify updates:

      Main menu:
        1) Update from GitHub
        2) Rollback last update
        3) View last update log
        4) Back

      Confirm sub-menu for actions:
        - Yes
        - No
    """

    UPDATE_SERVICE = ["sudo", "systemctl", "start", "quadify-update.service"]
    ROLLBACK_SCRIPT = "/home/volumio/Quadify/scripts/quadify_rollback.sh"
    UPDATE_LOG = Path("/var/log/quadify_update.log")

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

        self.main_items = [
            "Update from GitHub",
            "Rollback last update",
            "View last update log",
            "Back",
        ]
        self.confirm_items = ["Yes", "No"]

        self.current_list = self.main_items
        self.current_selection_index = 0

        # Which action are we confirming? ("update" | "rollback" | None)
        self._pending_action = None

    # ---------------------------
    # Lifecycle
    # ---------------------------
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

    # ---------------------------
    # Input handling
    # ---------------------------
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
            self.logger.debug(f"SystemUpdateMenu: Scrolled {old_index} -> {self.current_selection_index}")
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
                self._pending_action = "update"
                self._move_to_confirm(
                    "Update Quadify from GitHub?\nThis will stop and restart the app."
                )

            elif selected_item == "Rollback last update":
                self._pending_action = "rollback"
                self._move_to_confirm(
                    "Rollback to the previous version?\nThis will restart the app."
                )

            elif selected_item == "View last update log":
                self._show_update_log()

            elif selected_item == "Back":
                self.stop_mode()
                self.mode_manager.back()

        elif self.current_menu == "confirm":
            if selected_item == "Yes":
                # Execute the pending action
                action = self._pending_action
                self._pending_action = None
                if action == "update":
                    self._perform_update()
                elif action == "rollback":
                    self._perform_rollback()
                else:
                    self._notice("Nothing to do.")
            else:
                # Cancel -> back to main
                self._pending_action = None
                self._return_to_main()

    # ---------------------------
    # Actions
    # ---------------------------
    def _perform_update(self):
        # Splash “working” message with a simple animated dots loop
        self._progress_splash("Updating from GitHub\nPlease wait")

        # Fire the systemd service (non-blocking is fine; service handles pacing)
        try:
            subprocess.run(self.UPDATE_SERVICE, check=True)
            self.logger.info("SystemUpdateMenu: quadify-update.service started.")
        except subprocess.CalledProcessError as e:
            self.logger.exception("Failed to start update service")
            self._error("Update failed to start.\nSee the update log.")
            return

        # Brief progress animation (service runs independently)
        self._animate_for_seconds(3.0, base_text="Applying update")

        # Show a success note; the service restarts Quadify on its own
        self._notice("Update triggered.\nQuadify will restart shortly.")
        time.sleep(2)
        self.display_manager.show_logo()
        self.stop_mode()

    def _perform_rollback(self):
        self._progress_splash("Rolling back to previous version\nPlease wait")
        try:
            subprocess.run(["bash", self.ROLLBACK_SCRIPT], check=True)
        except subprocess.CalledProcessError:
            self.logger.exception("Rollback script failed")
            self._error("Rollback failed.\nSee the update log.")
            return

        self._animate_for_seconds(2.0, base_text="Restoring backup")
        self._notice("Rollback complete.\nRestarting Quadify…")
        time.sleep(2)
        self.display_manager.show_logo()
        self.stop_mode()

    def _show_update_log(self):
        # Tail the last few lines of the updater log (if it exists)
        lines = []
        if self.UPDATE_LOG.exists():
            try:
                out = subprocess.check_output(["tail", "-n", "10", str(self.UPDATE_LOG)], text=True)
                lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
            except Exception:
                self.logger.exception("Failed to read update log")
                lines = ["Could not read update log."]
        else:
            lines = ["No update log found yet."]

        # Render neatly on the display
        self.display_manager.clear_screen()

        def draw(draw_obj):
            y = 8
            draw_obj.text((6, y), "Last update log:", font=self.font, fill="white")
            y += 16
            for ln in lines[-6:]:
                draw_obj.text((6, y), ln[:22], font=self.font, fill="gray")  # short lines for small OLEDs
                y += 13
            # Hint to user
            draw_obj.text((6, y + 6), "Press BACK to return", font=self.font, fill="gray")

        self.display_manager.draw_custom(draw)

    # ---------------------------
    # UI helpers
    # ---------------------------
    def _move_to_confirm(self, message):
        self.current_menu = "confirm"
        self.current_list = self.confirm_items
        self.current_selection_index = 0
        self.window_start_index = 0

        # Show a centred confirm text before listing Yes/No
        self._message_screen(message)
        time.sleep(0.6)
        self._display_current_menu()

    def _return_to_main(self):
        self.current_menu = "main"
        self.current_list = self.main_items
        self.current_selection_index = 0
        self.window_start_index = 0
        self._display_current_menu()

    def _message_screen(self, text, fill="white"):
        self.display_manager.clear_screen()

        def draw(draw_obj):
            # Simple multi-line text block
            y = 18
            for ln in text.split("\n"):
                draw_obj.text((10, y), ln, font=self.font, fill=fill)
                y += 16

        self.display_manager.draw_custom(draw)

    def _progress_splash(self, text):
        self.display_manager.clear_screen()

        def draw(draw_obj):
            y = 18
            for ln in text.split("\n"):
                draw_obj.text((10, y), ln, font=self.font, fill="white")
                y += 16

        self.display_manager.draw_custom(draw)

    def _animate_for_seconds(self, seconds: float, base_text="Working"):
        # A tiny animated “...” for visual feedback
        start = time.time()
        dots = ["", ".", "..", "..."]
        idx = 0
        while time.time() - start < seconds:
            msg = f"{base_text}{dots[idx % len(dots)]}"
            self._message_screen(msg)
            idx += 1
            time.sleep(0.35)

    def _notice(self, text):
        self._message_screen(text, fill="white")

    def _error(self, text):
        self._message_screen(text, fill="white")
        # Optionally flash or hold a bit longer for errors
        time.sleep(2)

    # ---------------------------
    # Rendering the list
    # ---------------------------
    def _display_current_menu(self):
        if not self.is_active:
            return

        visible_items = self._get_visible_window(self.current_list, self.current_selection_index)

        def draw(draw_obj):
            # Title
            title = "System Update"
            draw_obj.text((5, 2), title, font=self.font, fill="white")

            # Items
            for i, item_name in enumerate(visible_items):
                actual_index = self.window_start_index + i
                is_selected = (actual_index == self.current_selection_index)

                arrow = "-> " if is_selected else "  "
                fill_colour = "white" if is_selected else "gray"
                y_pos = self.y_offset + 10 + i * self.line_spacing  # a little extra top padding

                draw_obj.text(
                    (5, y_pos),
                    f"{arrow}{item_name}",
                    font=self.font,
                    fill=fill_colour
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
