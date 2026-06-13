import subprocess
import os
import aiofiles
import httpx
from config import (
    SHOP_LOGO_PATH,
    SHOP_DETAILS_PATH,
    SHOP_DETAILS_DURATION,
    LOGO_POSITION,
    LOGO_SCALE,
    OUTPUT_RESOLUTION,
    TEMP_DIR,
    CLOUDINARY_UPLOAD_URL,
    CLOUDINARY_UPLOAD_PRESET,
)


def _run_ffmpeg(args: list) -> None:
    """Run an ffmpeg command, raise on failure."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")


def normalize_clip(clip_path: str, index: int) -> str:
    """
    Normalize each clip to same resolution, codec, fps.
    Required before concatenation.
    """
    output = os.path.join(TEMP_DIR, f"norm_{index:02d}.mp4")
    w, h = OUTPUT_RESOLUTION.split(":")
    _run_ffmpeg([
        "-i", clip_path,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-an",                  # no audio from LTX-2 clips (add music later)
        output,
    ])
    return output


def shop_details_to_clip() -> str:
    """Convert static shop details image into a short video clip."""
    output = os.path.join(TEMP_DIR, "shop_details_clip.mp4")
    w, h = OUTPUT_RESOLUTION.split(":")
    _run_ffmpeg([
        "-loop", "1",
        "-i", SHOP_DETAILS_PATH,
        "-t", str(SHOP_DETAILS_DURATION),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        output,
    ])
    return output


def concatenate_clips(clip_paths: list) -> str:
    """Concatenate all normalized clips into one video using concat demuxer."""
    list_file = os.path.join(TEMP_DIR, "clips_list.txt")
    output    = os.path.join(TEMP_DIR, "concatenated.mp4")

    with open(list_file, "w") as f:
        for path in clip_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    _run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output,
    ])
    return output


def overlay_logo(video_path: str) -> str:
    """Overlay shop logo watermark on one corner throughout the video."""
    output = os.path.join(TEMP_DIR, "with_logo.mp4")
    w, h   = LOGO_SCALE.split(":")
    x, y   = LOGO_POSITION.split(":")
    _run_ffmpeg([
        "-i", video_path,
        "-i", SHOP_LOGO_PATH,
        "-filter_complex",
        f"[1:v]scale={w}:{h}[logo];[0:v][logo]overlay={x}:{y}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        output,
    ])
    return output


def finalize_video(job_id: str) -> str:
    """
    Full stitching pipeline:
    1. Normalize all jewellery clips
    2. Convert shop details image to clip
    3. Concatenate everything
    4. Overlay logo
    Returns path to final output MP4.
    """
    import glob

    # Collect raw clips in order
    raw_clips = sorted(glob.glob(os.path.join(TEMP_DIR, "clip_*.mp4")))
    if not raw_clips:
        raise FileNotFoundError("No clips found in temp dir.")

    # Step 1: Normalize jewellery clips
    normalized = [normalize_clip(c, i) for i, c in enumerate(raw_clips)]

    # Step 2: Shop details clip
    details_clip = shop_details_to_clip()
    all_clips    = normalized + [details_clip]

    # Step 3: Concatenate
    concatenated = concatenate_clips(all_clips)

    # Step 4: Logo overlay
    final = overlay_logo(concatenated)

    # Copy to named output
    output_path = os.path.join(TEMP_DIR, f"ad_{job_id}.mp4")
    os.rename(final, output_path)

    return output_path


async def upload_to_cloudinary(video_path: str) -> str:
    """Upload final video to Cloudinary and return public URL."""
    upload_url    = CLOUDINARY_UPLOAD_URL
    upload_preset = CLOUDINARY_UPLOAD_PRESET

    async with aiofiles.open(video_path, "rb") as f:
        video_data = await f.read()

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            upload_url,
            data={"upload_preset": upload_preset},
            files={"file": (os.path.basename(video_path), video_data, "video/mp4")},
        )
        if response.status_code >= 400:
            print("Cloudinary error response:", response.text)
        response.raise_for_status()
        return response.json()["secure_url"]
