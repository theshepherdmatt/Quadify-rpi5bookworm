from display.display_manager import DisplayManager
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import math
import threading
import os
import time

# --- OLED/display setup ---
dummy_config = {}
display_manager = DisplayManager(dummy_config)

# --- VU meter image & settings ---
vuscreen_path = "/home/volumio/Quadify/src/assets/images/pngs/vuscreen.png"
bg_orig = Image.open(vuscreen_path).convert("RGBA")
width, height = bg_orig.size

def darken_image(img, amount=0.6):
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(amount)

# --- VU Needle parameters (tuned for your photo and screen) ---
left_centre = (54, 68)
right_centre = (200, 68)
needle_length = 28         # Shorter needle
min_angle = -55
max_angle = 55

# --- Text labels (set statically or from Volumio state if wanted) ---
title = "Test Song"
artist = "Test Artist"
font = ImageFont.load_default()

# --- FIFO path for CAVA (must match cava config!) ---
FIFO_PATH = "/tmp/display.fifo"

# --- Shared state ---
vu_state = {"left": 0, "right": 0, "exit": False}

def level_to_angle(level):
    """Convert 0-255 level to needle angle."""
    return min_angle + (level / 255) * (max_angle - min_angle)

def draw_needle(draw, centre, angle_deg, length, colour):
    """Draw a needle at given centre, angle (deg), and length."""
    angle_rad = math.radians(angle_deg - 90)  # -90: 0 deg points up
    x_end = int(centre[0] + length * math.cos(angle_rad))
    y_end = int(centre[1] + length * math.sin(angle_rad))
    draw.line([centre, (x_end, y_end)], fill=colour, width=2)

def read_fifo():
    """Read CAVA FIFO, update vu_state with averaged left/right."""
    while not vu_state["exit"]:
        if not os.path.exists(FIFO_PATH):
            time.sleep(0.25)
            continue
        try:
            with open(FIFO_PATH, "r") as fifo:
                while not vu_state["exit"]:
                    line = fifo.readline()
                    if line:
                        bars = [int(x) for x in line.strip().split(";") if x.isdigit()]
                        if len(bars) >= 36:
                            vu_state["left"] = sum(bars[:18]) // 18
                            vu_state["right"] = sum(bars[18:]) // 18
                    else:
                        time.sleep(0.01)
        except Exception as e:
            print("FIFO error:", e)
            time.sleep(1)

def render_loop():
    while not vu_state["exit"]:
        # --- Darken background each frame for contrast ---
        frame = darken_image(bg_orig.copy(), amount=0.6)
        draw = ImageDraw.Draw(frame)

        # --- Needles: pure white! ---
        draw_needle(draw, left_centre, level_to_angle(vu_state["left"]), needle_length, "white")
        draw_needle(draw, right_centre, level_to_angle(vu_state["right"]), needle_length, "white")

        # --- Song title and artist at the top, centred ---
        title_w, title_h = draw.textsize(title, font=font)
        artist_w, artist_h = draw.textsize(artist, font=font)
        title_y = 2
        artist_y = title_y + title_h + 2
        draw.text(((width - title_w)//2, title_y), title, font=font, fill="white")
        draw.text(((width - artist_w)//2, artist_y), artist, font=font, fill="white")

        frame = frame.convert(display_manager.oled.mode)
        display_manager.oled.display(frame)
        time.sleep(1/60.0)

# --- Start threads ---
fifo_thread = threading.Thread(target=read_fifo, daemon=True)
render_thread = threading.Thread(target=render_loop, daemon=True)
fifo_thread.start()
render_thread.start()

try:
    input("Press Enter to finish...")
finally:
    vu_state["exit"] = True
    fifo_thread.join(timeout=2)
    render_thread.join(timeout=2)
