"""Refresh the credited Unsplash showcase images (optional, network required)."""
import html
import re
import subprocess
from pathlib import Path

SAMPLES = {
    'fox.jpg': 'https://unsplash.com/photos/fox-laying-on-snow-qQUtvVdurHg',
    'alpine-lake.jpg': 'https://unsplash.com/photos/a-mountain-range-is-reflected-in-the-still-water-of-a-lake-37XGaPVDTEg',
    'fern.jpg': 'https://unsplash.com/photos/green-fern-plant-in-close-up-photography-KPfSQdeptbs',
    'butterfly.jpg': 'https://unsplash.com/photos/shallow-focus-photography-of-butterfly-on-flowers-7vjonHYnDco',
}


def download(url):
    # curl uses the platform certificate store, including macOS system roots.
    return subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                           '--max-time', '45', url], check=True, capture_output=True).stdout


if __name__ == '__main__':
    from PIL import Image
    from io import BytesIO
    destination = Path(__file__).resolve().parents[1] / 'docs' / 'samples'
    for filename, page in SAMPLES.items():
        markup = download(page).decode('utf-8')
        tag = re.search(r'<meta[^>]*property="og:image"[^>]*>', markup)
        if not tag:
            raise RuntimeError(f'No source image found for {page}')
        image_id = re.search(r'https://images\.unsplash\.com/(photo-[^?"&]+)', html.unescape(tag[0]))
        if not image_id:
            raise RuntimeError(f'Unexpected source URL for {page}')
        data = download(f'https://images.unsplash.com/{image_id[1]}?auto=format&fit=max&w=1600&q=88&fm=jpg')
        with Image.open(BytesIO(data)) as image:
            image.verify()
        (destination / filename).write_bytes(data)
        print(f'Validated {filename}: {len(data):,} bytes', flush=True)
