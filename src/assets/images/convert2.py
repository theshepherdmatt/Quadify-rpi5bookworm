import os
import requests
from io import BytesIO
from PIL import Image, ImageChops
import cairosvg
import sys

VOLUMIO_HOST = 'http://localhost:3000'
ASSETS_DIR = '/home/volumio/Quadify/src/assets/pngs'
ICON_SIZE = 50

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from network.service_listener import get_available_services

def trim_icon(image, crop_ratio=1.0):
    """Crop transparent padding from an RGBA image by cropping to a fraction of the bounding box centered on the icon."""
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    alpha = image.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return image  # no content, no crop

    left, upper, right, lower = bbox
    width = right - left
    height = lower - upper
    center_x = left + width / 2
    center_y = upper + height / 2

    new_width = width * crop_ratio
    new_height = height * crop_ratio

    new_left = max(0, int(center_x - new_width / 2))
    new_upper = max(0, int(center_y - new_height / 2))
    new_right = min(image.width, int(center_x + new_width / 2))
    new_lower = min(image.height, int(center_y + new_height / 2))

    return image.crop((new_left, new_upper, new_right, new_lower))

def resize_with_aspect_ratio(img, target_size):
    img.thumbnail((target_size, target_size), Image.ANTIALIAS)
    background = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
    x = (target_size - img.width) // 2
    y = (target_size - img.height) // 2
    background.paste(img, (x, y))
    return background

def download_and_convert_icon(url, save_path):
    try:
        print(f"Downloading {url}")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get('Content-Type', '')
        
        if 'svg' in content_type:
            cairosvg.svg2png(bytestring=resp.content, write_to=save_path, output_width=ICON_SIZE, output_height=ICON_SIZE)
            print(f"Converted and saved SVG as PNG: {save_path}")
        else:
            img = Image.open(BytesIO(resp.content))
            img = img.convert("RGBA")
            img = trim_icon(img, crop_ratio=1.5) # crop_ratio=1 means no extra crop scaling
            img = resize_with_aspect_ratio(img, ICON_SIZE)
            img.save(save_path, format='PNG')
            print(f"Downloaded, trimmed, resized image saved: {save_path}")
    except Exception as e:
        print(f"Failed to process {url}: {e}")

def main():
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR)

    services = get_available_services()
    seen_names = set()

    for svc in services:
        label = svc['name'].upper().replace(' ', '_')
        if label in seen_names:
            continue
        seen_names.add(label)

        icon_url = svc.get('icon_url') or svc.get('albumart')
        if not icon_url:
            print(f"No icon URL for {label}, skipping.")
            continue

        if icon_url.startswith('/'):
            icon_url = VOLUMIO_HOST + icon_url

        save_path = os.path.join(ASSETS_DIR, f"{label}.png")
        if os.path.exists(save_path):
            print(f"Icon already exists: {save_path}, skipping download.")
            continue
        
        download_and_convert_icon(icon_url, save_path)

if __name__ == "__main__":
    main()
