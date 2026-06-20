import httpx
import aiofiles
import os
import random
from urllib.parse import quote
from config import POLLINATIONS_API_URL, POLLINATIONS_API_KEY, TEMP_DIR

MUSIC_STYLES = [
    "soft elegant piano with light strings, luxury ambient",
    "warm acoustic guitar, gentle and uplifting, boutique feel",
    "dreamy lo-fi with soft chimes, calm and modern",
    "smooth jazz lounge, sophisticated and relaxed",
    "ambient synth with soft pads, premium and minimal",
    "light orchestral strings, elegant and cinematic",
    "soft marimba and bells, cheerful and warm",
    "chill electronic beat, modern and stylish",
]


async def generate_music(duration: float) -> str:
    """
    Generate background music using Pollinations 'acestep' model.
    Picks a random style from MUSIC_STYLES.
    Returns path to downloaded MP3 file.
    """
    style = random.choice(MUSIC_STYLES)
    print(f"[INFO] Music style selected: {style}")

    os.makedirs(TEMP_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, "music.mp3")

    duration_int = max(3, int(duration) + 1)

    url = f"{POLLINATIONS_API_URL}/audio/{quote(style)}"
    params = {
        "model": "acestep",
        "duration": str(duration_int),
        "instrumental": "true",
        "style": style,
    }

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"},
        )
        response.raise_for_status()

    async with aiofiles.open(output_path, "wb") as f:
        await f.write(response.content)

    return output_path
