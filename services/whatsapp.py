import httpx
import aiofiles
import os
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_NUMBER,
    TEMP_DIR,
)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Keywords
TRIGGER_KEYWORD = "make ad"
CANCEL_KEYWORD  = "cancel"


def send_message(to: str, body: str) -> None:
    """Send a plain text WhatsApp message to dad."""
    # WhatsApp/Twilio caps messages at 1600 characters
    if len(body) > 1600:
        body = body[:1550] + "\n...(truncated)"

    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=body,
    )


def send_video(to: str, video_path: str, caption: str = "") -> None:
    """Send the final video ad back to dad on WhatsApp."""
    # Twilio requires a publicly accessible URL for media.
    # In production, upload to Cloudinary/S3 first and pass the URL here.
    # For local dev, use ngrok to expose a static file endpoint.
    raise NotImplementedError(
        "Upload video to Cloudinary or S3 first, then pass public URL here."
    )


def send_video_url(to: str, media_url: str, caption: str = "") -> None:
    """Send video via public URL (use this in production)."""
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=caption,
        media_url=[media_url],
    )


async def download_image(media_url: str, filename: str) -> str:
    """Download an image from Twilio media URL and save to temp dir."""
    import asyncio
    os.makedirs(TEMP_DIR, exist_ok=True)
    save_path = os.path.join(TEMP_DIR, filename)

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

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(response.content)

    return save_path


def parse_incoming(form_data: dict) -> dict:
    """
    Parse Twilio webhook form data into a clean dict.
    Returns sender, body text, and list of media URLs.
    """
    sender     = form_data.get("From", "")
    body       = form_data.get("Body", "").strip().lower()
    num_media  = int(form_data.get("NumMedia", 0))

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
