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


def concatenate_clips(clip_paths: list, output_name: str = "concatenated.mp4") -> str:
    """Concatenate clips into one video using concat demuxer."""
    list_file = os.path.join(TEMP_DIR, f"{output_name}_list.txt")
    output    = os.path.join(TEMP_DIR, output_name)

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


def get_duration(video_path: str) -> float:
    """Return duration of a video file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error:\n{result.stderr}")
    return float(result.stdout.strip())


def add_music(video_path: str, music_path: str) -> str:
    """
    Overlay background music onto the video.
    Music is trimmed to match video duration, with a short fade-out at the end.
    """
    output   = os.path.join(TEMP_DIR, "with_music.mp4")
    duration = get_duration(video_path)
    fade_start = max(duration - 1.5, 0)

    _run_ffmpeg([
        "-i", video_path,
        "-i", music_path,
        "-filter_complex",
        f"[1:a]atrim=0:{duration},afade=t=out:st={fade_start}:d=1.5[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output,
    ])
    return output


async def finalize_video(job_id: str, generate_music_fn=None) -> str:
    """
    Full stitching pipeline:
    1. Normalize all jewellery clips
    2. Concatenate jewellery clips
    3. Overlay logo (jewellery clips only, NOT shop details)
    4. Convert shop details image to clip
    5. Concatenate logo'd jewellery clip + shop details clip
    6. (Optional) Generate and overlay background music matching actual duration
    Returns path to final output MP4.

    generate_music_fn: optional async callable(duration: float) -> str (path to mp3)
    """
    import glob

    # Collect raw clips in order
    raw_clips = sorted(glob.glob(os.path.join(TEMP_DIR, "clip_*.mp4")))
    if not raw_clips:
        raise FileNotFoundError("No clips found in temp dir.")

    # Step 1: Normalize jewellery clips
    normalized = [normalize_clip(c, i) for i, c in enumerate(raw_clips)]

    # Step 2: Concatenate jewellery clips
    jewellery_concat = concatenate_clips(normalized) if len(normalized) > 1 else normalized[0]

    # Step 3: Logo overlay (jewellery clips only)
    with_logo = overlay_logo(jewellery_concat)

    # Step 4: Shop details clip (no logo)
    details_clip = shop_details_to_clip()

    # Step 5: Concatenate logo'd jewellery clip + shop details clip
    final = concatenate_clips([with_logo, details_clip], output_name="final_concat.mp4")

    # Step 6: Music overlay (optional), based on actual final duration
    if generate_music_fn:
        try:
            duration   = get_duration(final)
            music_path = await generate_music_fn(duration)
            if music_path and os.path.exists(music_path):
                final = add_music(final, music_path)
        except Exception as music_err:
            print(f"[WARN] Music generation failed, continuing without music: {music_err}")

    # Copy to named output
    output_path = os.path.join(TEMP_DIR, f"ad_{job_id}.mp4")
    os.replace(final, output_path)

    return output_path


def cleanup_temp(keep: list = None) -> None:
    """
    Delete all files in TEMP_DIR except those in `keep` (basenames).
    Used after sending the final video to free up space.
    """
    import glob

    keep = set(keep or [])
    for path in glob.glob(os.path.join(TEMP_DIR, "*")):
        if os.path.basename(path) not in keep and os.path.isfile(path):
            os.remove(path)


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
