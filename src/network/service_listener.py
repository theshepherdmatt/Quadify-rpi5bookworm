import os
import requests
import logging
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

def download_and_cache_icon(icon_url, save_dir, save_name):
    if not icon_url or not icon_url.startswith("http"):
        logger.info(f"No valid icon URL: {icon_url}")
        return None
    os.makedirs(save_dir, exist_ok=True)
    dest_path = os.path.join(save_dir, f"{save_name}.png")
    if os.path.exists(dest_path):
        logger.info(f"Icon already exists: {dest_path}, skipping download.")
        return dest_path
    try:
        logger.info(f"Downloading icon: {icon_url}")
        r = requests.get(icon_url, timeout=4)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.save(dest_path)
        logger.info(f"Saved icon to: {dest_path}")
        return dest_path
    except Exception as e:
        logger.warning(f"Failed to download/save icon {icon_url}: {e}")
        return None

def get_available_services():
    VOLUMIO_HOST = 'http://localhost:3000'
    ROOT_URL = f'{VOLUMIO_HOST}/api/v1/browse?uri='
    MUSICLIB_URL = f'{VOLUMIO_HOST}/api/v1/browse?uri=music-library'
    result = []
    icon_folder_base = '/home/volumio/Quadify/src/assets/pngs'

    # Fetch top-level services
    logger.info("Requesting Volumio root music services from: %s", ROOT_URL)
    try:
        r = requests.get(ROOT_URL, timeout=5)
        r.raise_for_status()
        data = r.json()
        for item in data.get('navigation', {}).get('lists', []):
            name = item.get('name') or item.get('title', 'UNKNOWN')
            plugin = item.get('plugin_name', item.get('service', 'unknown'))
            uri = item.get('uri', 'N/A')
            albumart = item.get('albumart', None)
            icon_url = f"http://localhost:3000{albumart}" if albumart and albumart.startswith("/") else albumart
            # Use radioicons for radio, else pngs
            save_dir = os.path.join(icon_folder_base, 'radioicons') if 'radio' in (name or '').lower() else icon_folder_base
            save_name = name.upper().replace(" ", "_").replace("/", "_")
            if icon_url:
                download_and_cache_icon(icon_url, save_dir, save_name)
            result.append({
                'name': name,
                'plugin': plugin,
                'uri': uri,
                'albumart': albumart
            })
    except Exception as e:
        logger.error("Failed to query Volumio API (root): %s", e)
        return []

    # Look for "music-library", then fetch its children
    for svc in result[:]:  # iterate a copy
        if svc['uri'] == "music-library":
            logger.info("Querying inside Music Library for subfolders/services.")
            try:
                ml_r = requests.get(MUSICLIB_URL, timeout=5)
                ml_r.raise_for_status()
                ml_data = ml_r.json()
                for group in ml_data.get('navigation', {}).get('lists', []):
                    for item in group.get('items', []):
                        name = item.get('title', item.get('name', 'UNKNOWN'))
                        plugin = item.get('plugin_name', item.get('service', 'mpd'))
                        uri = item.get('uri', 'N/A')
                        albumart = item.get('albumart', None)
                        icon_url = f"http://localhost:3000{albumart}" if albumart and albumart.startswith("/") else albumart
                        save_dir = os.path.join(icon_folder_base, 'radioicons') if 'radio' in (name or '').lower() else icon_folder_base
                        save_name = name.upper().replace(" ", "_").replace("/", "_")
                        if icon_url:
                            download_and_cache_icon(icon_url, save_dir, save_name)
                        result.append({
                            'name': name,
                            'plugin': plugin,
                            'uri': uri,
                            'albumart': albumart
                        })
            except Exception as e:
                logger.error("Failed to query Music Library: %s", e)

    logger.info("Found %d music services (including subfolders).", len(result))
    return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    services = get_available_services()
    print("Available services:")
    for svc in services:
        icon = svc['albumart']
        icon_url = f"http://localhost:3000{icon}" if icon else "None"
        print(f" - {svc['name']:20} | Plugin: {svc['plugin']:10} | URI: {svc['uri']:25} | Icon: {icon_url}")
