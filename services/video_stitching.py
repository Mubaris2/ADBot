"""
video_stitching.py — Railway side.
All heavy FFmpeg work is offloaded to Modal via HTTP POST.
Sensitive keys (Cloudinary, Pollinations) live in Modal secrets, not here.
"""

import httpx
import os
import base64
from config import (
    SHOP_LOGO_PATH,
    SHOP_DETAILS_PATH,
    SHOP_DETAILS_DURATION,
    LOGO_POSITION,
    LOGO_SCALE,
    OUTPUT_RESOLUTION,
    MODAL_ENDPOINT_URL,
)


def _read_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def process_and_upload_video(
    image_urls: list[str],
) -> str:
    """
    Send image Cloudinary URLs + static assets to Modal for processing.
    Modal handles FFmpeg pipeline, Cloudinary upload, returns video URL.
    """
    if not MODAL_ENDPOINT_URL:
        raise RuntimeError("MODAL_ENDPOINT_URL not set in environment variables.")

    if not os.path.exists(SHOP_LOGO_PATH):
        raise FileNotFoundError(f"Shop logo not found at {SHOP_LOGO_PATH}")
    if not os.path.exists(SHOP_DETAILS_PATH):
        raise FileNotFoundError(f"Shop details not found at {SHOP_DETAILS_PATH}")

    payload = {
        # Cloudinary URLs of collected jewellery images
        "image_urls":            image_urls,

        # Static assets sent as base64 (small files, fine to inline)
        "logo_b64":              _read_b64(SHOP_LOGO_PATH),
        "shop_details_b64":      _read_b64(SHOP_DETAILS_PATH),

        # Video config
        "output_resolution":     OUTPUT_RESOLUTION,
        "logo_scale":            LOGO_SCALE,
        "logo_position":         LOGO_POSITION,
        "shop_details_duration": SHOP_DETAILS_DURATION,

    }

    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        response = await client.post(MODAL_ENDPOINT_URL, json=payload)
        if response.status_code >= 400:
            print(f"[ERROR] Modal endpoint error: {response.text}")
        response.raise_for_status()

    return response.json()["url"]


def cleanup_temp(keep: list = None) -> None:
    import glob
    from config import TEMP_DIR

    keep = set(keep or [])
    for path in glob.glob(os.path.join(TEMP_DIR, "*")):
        if os.path.basename(path) not in keep and os.path.isfile(path):
            os.remove(path)
