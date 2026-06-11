import httpx
import asyncio
import os
import aiofiles
from urllib.parse import quote
from config import (
    POLLINATIONS_API_URL,
    POLLINATIONS_API_KEY,
    VIDEO_DURATION_SEC,
    TEMP_DIR,
)


async def generate_video(image_url: str, scene_prompt: str, index: int) -> str:
    """
    Call Pollinations LTX-2 video generation (GET-based API).
    image_url must be a publicly accessible URL (e.g. Cloudinary).
    Returns path to downloaded video clip.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"clip_{index:02d}.mp4")

    encoded_prompt = quote(scene_prompt)

    params = {
        "model": "ltx-2",
        "image": image_url,
        "duration": str(VIDEO_DURATION_SEC),
        "audio": "false",
    }

    url = f"{POLLINATIONS_API_URL}/video/{encoded_prompt}"

    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"},
        )
        response.raise_for_status()

    async with aiofiles.open(output_path, "wb") as f:
        await f.write(response.content)

    return output_path


async def generate_all_videos(image_urls: list, scene_prompts: list) -> list:
    """
    Generate video clips for all images sequentially.
    image_urls must be publicly accessible URLs.
    Returns ordered list of clip paths.
    """
    clips = []
    for i, (image_url, prompt) in enumerate(zip(image_urls, scene_prompts)):
        print(f"Generating clip {i + 1}/{len(image_urls)}: {prompt[:40]}...")
        clip_path = await generate_video(image_url, prompt, index=i)
        clips.append(clip_path)

        if i < len(image_urls) - 1:
            await asyncio.sleep(2)

    return clips

