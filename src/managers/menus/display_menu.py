import logging
import time
from PIL import ImageFont
from managers.menus.base_manager import BaseManager

class DisplayMenu(BaseManager):
    """
    ... (keep your docstring as is, or update with Modern-VU Styles submenu)
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

        self.spectrum_enabled = bool(mode_manager.config.get("cava_enabled", True))

        # Menus
        self.main_items = [
            "Display Modes",
            "Brightness",
            "Screensaver",
            "Back"
        ]
        self.display_modes_items = [
            "VU-Meters",
            "Simple",
            self._get_spectrum_label()
        ]
        self.vu_meter_modes = ["Modern-VU", "Classic-VU", "Digi-VU"]
        self.modern_vu_styles = ["Bars", "Dots", "Oscilloscope"]
        self.simple_modes = ["Minimal", "Original"]
        self.brightness_items = ["Low", "Medium", "High"]
        self.screensaver_items = [
            "None",
            "Snake",
            "Geo",
            "Quadify",
            "Timer",
            "Back"
        ]
        self.screensaver_timer_items = [
            ("1 min",   60),
            ("2 min",   120),
            ("5 min",   300),
            ("10 min",  600),
            ("1 hour",  3600),
        ]

        self.menus = {
            "main": self.main_items,
            "display_modes": self.display_modes_items,
            "vu_meters": self.vu_meter_modes,
            "modern_vu_styles": self.modern_vu_styles,
            "simple": self.simple_modes,
            "brightness": self.brightness_items,
            "screensaver": self.screensaver_items,
            "screensaver_timer": [x[0] for x in self.screensaver_timer_items]
        }

        self.current_list = self.main_items
        self.current_selection_index = 0

    # ------------------------------------------------------------
    def start_mode(self):
        if self.is_active:
            return
        self.is_active = True
        self._show_menu("main")

    def stop_mode(self):
        if self.is_active:
            self.is_active = False
            self.display_manager.clear_screen()
            self.logger.info("DisplayMenu: Stopped and cleared display.")

    # ------------------------------------------------------------
    def scroll_selection(self, direction):
        if not self.is_active:
            return
        if time.time() - self.last_action_time < self.debounce_interval:
            return
        self.last_action_time = time.time()

        n = len(self.current_list)
        prev = self.current_selection_index
        self.current_selection_index = min(max(self.current_selection_index + direction, 0), n - 1)
        if self.current_selection_index != prev:
            self._display_current_menu()

    def select_item(self):
        if not self.is_active:
            return
        if time.time() - self.last_action_time < self.debounce_interval:
            return
        self.last_action_time = time.time()

        sel = self.current_list[self.current_selection_index]

        # --- Main Menu ---
        if self.current_menu == "main":
            if sel == "Display Modes":
                self._show_menu("display_modes")
            elif sel == "Brightness":
                self._show_menu("brightness")
            elif sel == "Screensaver":
                self._show_menu("screensaver")
            elif sel == "Back":
                self.stop_mode()
                self.mode_manager.back()

        # --- Display Modes ---
        elif self.current_menu == "display_modes":
            if sel == "VU-Meters":
                self._show_menu("vu_meters")
            elif sel == "Simple":
                self._show_menu("simple")
            elif sel.startswith("Spectrum:"):
                self.spectrum_enabled = not self.spectrum_enabled
                self.mode_manager.config["cava_enabled"] = self.spectrum_enabled
                self.mode_manager.save_preferences()
                self.logger.info(f"DisplayMenu: Spectrum => {'On' if self.spectrum_enabled else 'Off'}")
                self.display_modes_items[-1] = self._get_spectrum_label()
                self._show_menu("display_modes")

        elif self.current_menu == "vu_meters":
            if sel == "Modern-VU":
                self._show_menu("modern_vu_styles")
            else:
                self._handle_display_mode(sel)
                self._show_menu("main")

        elif self.current_menu == "modern_vu_styles":
            self._handle_modern_vu_style(sel)
            self._show_menu("main")

        elif self.current_menu == "simple":
            self._handle_display_mode(sel)
            self._show_menu("main")

        # --- Brightness ---
        elif self.current_menu == "brightness":
            self._handle_brightness(sel)
            self._show_menu("main")

        # --- Screensaver ---
        elif self.current_menu == "screensaver":
            if sel == "Timer":
                self._show_menu("screensaver_timer")
            elif sel == "Back":
                self._show_menu("main")
            else:
                self._handle_screensaver(sel)
                self._show_menu("main")

        # --- Screensaver Timer Sub-menu ---
        elif self.current_menu == "screensaver_timer":
            self._handle_screensaver_timer(sel)
            self._show_menu("main")

    # ------------------------------------------------------------
    def _show_menu(self, menu_name):
        self.current_menu = menu_name
        if menu_name == "display_modes":
            self.display_modes_items[-1] = self._get_spectrum_label()
            self.current_list = self.display_modes_items
        else:
            self.current_list = self.menus[menu_name]
        self.current_selection_index = 0
        self.window_start_index = 0
        self._display_current_menu()

    def _display_current_menu(self):
        if not self.is_active:
            return
        visible = self._get_visible_window(self.current_list, self.current_selection_index)
        def draw(draw_obj):
            for i, name in enumerate(visible):
                actual_index = self.window_start_index + i
                selected = (actual_index == self.current_selection_index)
                # Right arrows for submenus
                submenu_arrow = ""
                if (self.current_menu == "display_modes" and name in ["VU-Meters", "Simple"]) or \
                   (self.current_menu == "vu_meters" and name == "Modern-VU") or \
                   (self.current_menu == "screensaver" and name == "Timer"):
                    submenu_arrow = " ->"
                arrow = "<- " if (self.current_menu == "main" and selected and name == "Back") else ("-> " if selected else "   ")
                fill = "white" if selected else "gray"
                y = self.y_offset + i * self.line_spacing
                draw_obj.text((5, y), f"{arrow}{name}{submenu_arrow}", font=self.font, fill=fill)
        self.display_manager.draw_custom(draw)

    def _get_visible_window(self, items, selected_index):
        total = len(items)
        half = self.window_size // 2
        start = max(min(selected_index - half, total - self.window_size), 0)
        self.window_start_index = start
        return items[start:start + self.window_size]

    def _get_spectrum_label(self):
        return f"Spectrum: {'On' if self.spectrum_enabled else 'Off'}"

    # ------------------------------------------------------------
    def _handle_display_mode(self, mode_name):
        mapping = {
            "Modern-VU":   "modern",
            "Classic-VU":  "vuscreen",
            "Digi-VU":     "digitalvuscreen",
            "Minimal":     "minimal",
            "Original":    "original"
        }
        val = mapping.get(mode_name)
        if val:
            self.logger.info(f"DisplayMenu: Setting display mode => {val}")
            self.mode_manager.set_display_mode(val)
        else:
            self.logger.warning(f"DisplayMenu: Unknown display mode => {mode_name}")

    def _handle_modern_vu_style(self, style_name):
        style_map = {
            "Bars": "bars",
            "Dots": "dots",
            "Oscilloscope": "scope"
        }
        selected = style_map.get(style_name)
        if selected:
            self.logger.info(f"DisplayMenu: Setting Modern-VU spectrum mode => {selected}")
            self.mode_manager.config["modern_spectrum_mode"] = selected
            self.mode_manager.save_preferences()
        else:
            self.logger.warning(f"DisplayMenu: Unknown Modern-VU style => {style_name}")

    def _handle_brightness(self, level):
        brightness_map = {"Low": 50, "Medium": 150, "High": 255}
        val = brightness_map.get(level)
        if val is not None and hasattr(self.display_manager.oled, "contrast"):
            try:
                self.display_manager.oled.contrast(val)
                self.logger.info(f"DisplayMenu: Brightness => {level} ({val})")
            except Exception as e:
                self.logger.error(f"DisplayMenu: Failed to set brightness => {e}")
            self.mode_manager.config["oled_brightness"] = val
            self.mode_manager.save_preferences()
        else:
            self.logger.warning(f"DisplayMenu: Unknown brightness => {level}")

    def _handle_screensaver(self, sel):
        saver_map = {
            "None":    "none",
            "Snake":   "snake",
            "Geo":     "geo",
            "Quadify": "quadify"
        }
        chosen = saver_map.get(sel, "none")
        self.mode_manager.config["screensaver_type"] = chosen
        self.logger.info(f"DisplayMenu: screensaver_type => {chosen}")
        self.mode_manager.save_preferences()

    def _handle_screensaver_timer(self, sel):
        for label, seconds in self.screensaver_timer_items:
            if sel == label:
                self.mode_manager.config["screensaver_timeout"] = seconds
                self.logger.info(f"DisplayMenu: screensaver_timeout => {label} ({seconds}s)")
                self.mode_manager.save_preferences()
                break

    def back(self):
        if self.is_active:
            self.stop_mode()
        self.mode_manager.back()
