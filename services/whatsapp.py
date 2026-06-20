import asyncio
import httpx
import os
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_NUMBER,
    CLOUDINARY_BASE_URL,
    CLOUDINARY_UPLOAD_PRESET,
    TEMP_DIR,
)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Keywords
TRIGGER_KEYWORD = "make ad"
CANCEL_KEYWORD  = "cancel"


def send_message(to: str, body: str) -> None:
    """Send a plain text WhatsApp message to dad."""
    if len(body) > 1600:
        body = body[:1550] + "\n...(truncated)"
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=body,
    )


def send_video_url(to: str, media_url: str, caption: str = "") -> None:
    """Send video via public Cloudinary URL."""
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=caption,
        media_url=[media_url],
    )


async def download_and_upload_image(media_url: str, filename: str) -> str:
    """
    Download image from Twilio (with 404 retry for race condition),
    then upload to Cloudinary and return the public Cloudinary URL.
    Local file is cleaned up after upload.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_DIR, filename)

    # Step 1: Download from Twilio with retry on 404
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    MAX_ATTEMPTS = 5
    for attempt in range(MAX_ATTEMPTS):
        async with httpx.AsyncClient(auth=auth, follow_redirects=True) as http:
            response = await http.get(media_url)
            if response.status_code == 404 and attempt < MAX_ATTEMPTS - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                print(f"[WARN] Twilio media 404 on attempt {attempt + 1}, retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            break

    with open(local_path, "wb") as f:
        f.write(response.content)

    # Step 2: Upload to Cloudinary image endpoint
    upload_url = CLOUDINARY_BASE_URL.rstrip("/") + "/image/upload"
    try:
        with open(local_path, "rb") as f:
            image_data = f.read()

        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                upload_url,
                data={"upload_preset": CLOUDINARY_UPLOAD_PRESET},
                files={"file": (filename, image_data, "image/png")},
            )
            if resp.status_code >= 400:
                print(f"[ERROR] Cloudinary image upload error: {resp.text}")
            resp.raise_for_status()
            cloudinary_url = resp.json()["secure_url"]

    finally:
        # Clean up local file regardless of upload success
        if os.path.exists(local_path):
            os.remove(local_path)

    return cloudinary_url


def parse_incoming(form_data: dict) -> dict:
    """Parse Twilio webhook form data into a clean dict."""
    sender    = form_data.get("From", "")
    body      = form_data.get("Body", "").strip().lower()
    num_media = int(form_data.get("NumMedia", 0))

    media_urls = [
        form_data.get(f"MediaUrl{i}", "")
        for i in range(num_media)
    ]

    return {
        "sender":     sender,
        "body":       body,
        "num_media":  num_media,
        "media_urls": media_urls,
        "is_trigger": body == TRIGGER_KEYWORD,
        "is_cancel":  body == CANCEL_KEYWORD,
        "has_images": num_media > 0,
    }
