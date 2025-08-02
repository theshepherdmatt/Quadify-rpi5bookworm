import os
from PIL import Image

ICON_SIZE = 40
ASSETS_DIR = '/home/volumio/Quadify/src/assets/pngs/radioicons'

def trim_icon(image, crop_ratio=1.0):
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    alpha = image.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return image  # Fully transparent or no alpha channel
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
    img.thumbnail((target_size, target_size), Image.LANCZOS)
    background = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
    x = (target_size - img.width) // 2
    y = (target_size - img.height) // 2
    background.paste(img, (x, y), img)
    return background

def process_folder(folder):
    for fname in os.listdir(folder):
        if not fname.lower().endswith('.png'):
            continue
        fpath = os.path.join(folder, fname)
        img = Image.open(fpath)
        img = trim_icon(img, crop_ratio=1.0)     # 1.0 = tight crop, try 1.2 for more space
        img = resize_with_aspect_ratio(img, ICON_SIZE)
        img.save(fpath, format='PNG')
        print(f"Processed: {fname}")

if __name__ == "__main__":
    process_folder(ASSETS_DIR)
