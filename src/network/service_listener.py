import requests
import logging

logger = logging.getLogger(__name__)

def get_available_services():
    VOLUMIO_HOST = 'http://localhost:3000'
    ROOT_URL = f'{VOLUMIO_HOST}/api/v1/browse?uri='
    MUSICLIB_URL = f'{VOLUMIO_HOST}/api/v1/browse?uri=music-library'
    result = []

    # Fetch top-level
    logger.info("Requesting Volumio root music services from: %s", ROOT_URL)
    try:
        r = requests.get(ROOT_URL, timeout=5)
        r.raise_for_status()
        data = r.json()
        for item in data.get('navigation', {}).get('lists', []):
            result.append({
                'name': item.get('name') or item.get('title', 'UNKNOWN'),
                'plugin': item.get('plugin_name', item.get('service', 'unknown')),
                'uri': item.get('uri', 'N/A'),
                'albumart': item.get('albumart', None)
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
                        result.append({
                            'name': item.get('title', item.get('name', 'UNKNOWN')),
                            'plugin': item.get('plugin_name', item.get('service', 'mpd')),
                            'uri': item.get('uri', 'N/A'),
                            'albumart': item.get('albumart', None)
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
