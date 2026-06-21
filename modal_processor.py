"""
modal_processor.py — deploy this to Modal, NOT Railway.

Deploy command:
    modal deploy modal_processor.py

Setup Modal secrets BEFORE deploying (one-time):
    modal secret create jewellery-ad-secrets \
        CLOUDINARY_BASE_URL=https://api.cloudinary.com/v1_1/<cloud> \
        CLOUDINARY_UPLOAD_PRESET=your_preset \
        POLLINATIONS_API_KEY=your_key

After deploy, copy the printed endpoint URL into Railway env as MODAL_ENDPOINT_URL.

Payload received from Railway:
  - image_urls: list of Cloudinary image URLs (jewellery photos)
  - logo_b64: base64 shop logo PNG
  - shop_details_b64: base64 shop details PNG
  - output_resolution, logo_scale, logo_position, shop_details_duration
  - music_theme: optional string

Returns JSON: {"url": "<cloudinary video URL>"}
"""

import modal
import os

app = modal.App("jewellery-ad-bot")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("pillow", "httpx", "fastapi[standard]")
)


@app.function(
    image=image,
    cpu=4,
    memory=2048,
    timeout=300,
    secrets=[modal.Secret.from_name("jewellery-ad-secrets")],
)
@modal.fastapi_endpoint(method="POST")
async def process_video(payload: dict) -> dict:
    import os
    import tempfile

    # Secrets available as env vars inside Modal container
    cdn_base   = os.environ["CLOUDINARY_BASE_URL"].rstrip("/")
    cdn_preset = os.environ["CLOUDINARY_UPLOAD_PRESET"]
    poll_key   = os.environ.get("POLLINATIONS_API_KEY")

    with tempfile.TemporaryDirectory() as tmp:

        # ── Download jewellery images from Cloudinary ───────────────────────
        image_paths = await _download_images(payload["image_urls"], tmp)

        # ── Decode static assets from base64 ───────────────────────────────
        logo_path    = _decode_b64(payload["logo_b64"],         os.path.join(tmp, "shop_logo.png"))
        details_path = _decode_b64(payload["shop_details_b64"], os.path.join(tmp, "shop_details.png"))

        # ── Config from payload ─────────────────────────────────────────────
        resolution       = payload.get("output_resolution",     "720:1280")
        logo_scale       = payload.get("logo_scale",            "100:100")
        logo_position    = payload.get("logo_position",         "610:1170")
        details_duration = payload.get("shop_details_duration", 4)


        # ── Ken Burns clips ─────────────────────────────────────────────────
        kb_clips = [
            _create_ken_burns_clip(p, i, tmp, resolution)
            for i, p in enumerate(image_paths)
        ]

        # ── Concat → normalize → logo → shop details → final concat ────────
        ornament  = _concat_clips(kb_clips,            os.path.join(tmp, "ornament.mp4"))
        norm      = _normalize_clip(ornament,           os.path.join(tmp, "norm.mp4"), resolution)
        with_logo = _overlay_logo(norm, logo_path,      os.path.join(tmp, "with_logo.mp4"), logo_scale, logo_position)
        details   = _shop_details_clip(details_path,    os.path.join(tmp, "details.mp4"), resolution, details_duration)
        final     = _concat_clips([with_logo, details], os.path.join(tmp, "final.mp4"))

        # ── Music ───────────────────────────────────────────────────────────
        if poll_key:
            try:
                duration   = _get_duration(final)
                music_path = await _generate_music(duration, poll_key, tmp)
                if music_path and os.path.exists(music_path):
                    final  = _add_music(final, music_path, os.path.join(tmp, "with_music.mp4"))
            except Exception as e:
                print(f"[WARN] Music failed, continuing without: {e}")

        # ── Upload final video to Cloudinary ────────────────────────────────
        video_url = await _upload_video(final, cdn_base, cdn_preset)
        return {"url": video_url}


# ── Helpers: download ───────────────────────────────────────────────────────

import httpx


async def _download_images(urls: list[str], tmp: str) -> list[str]:
    paths = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            resp = await client.get(url)
            resp.raise_for_status()
            path = os.path.join(tmp, f"img_{i}.png")
            with open(path, "wb") as f:
                f.write(resp.content)
            paths.append(path)
    return paths


def _decode_b64(b64_str: str, output_path: str) -> str:
    import base64
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(b64_str))
    return output_path


# ── Helpers: FFmpeg ─────────────────────────────────────────────────────────

import subprocess
import random
from PIL import Image

KEN_BURNS_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"]
FPS            = 20
IMAGE_DURATION = 2.3


def _run_ffmpeg(args: list) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-nostdin"] + args,
        capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")


def _ensure_reasonable_size(path: str, tmp: str, max_dim: int = 768) -> str:
    with Image.open(path) as img:
        if max(img.size) <= max_dim:
            return path
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        out = os.path.join(tmp, f"resized_{os.path.basename(path)}")
        img.convert("RGB").save(out, "PNG")
        return out


def _zoompan_filter(preset: str, w: int, h: int, frames: int) -> str:
    sw, sh = int(w * 1.3), int(h * 1.3)
    if preset == "zoom_in":
        z = "min(zoom+0.0015,1.2)";                   x = "(iw-ow)/2";                y = "(ih-oh)/2"
    elif preset == "zoom_out":
        z = "if(eq(on,0),1.2,max(zoom-0.0015,1.0))"; x = "(iw-ow)/2";                y = "(ih-oh)/2"
    elif preset == "pan_left":
        z = "1.1";                                     x = f"(iw-ow)*(1-on/{frames})"; y = "(ih-oh)/2"
    elif preset == "pan_right":
        z = "1.1";                                     x = f"(iw-ow)*(on/{frames})";   y = "(ih-oh)/2"
    else:  # diagonal
        z = "min(zoom+0.001,1.15)";                   x = f"(iw-ow)*(on/{frames})";   y = f"(ih-oh)*(on/{frames})"
    return (
        f"scale={sw}:{sh},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS}"
    )


def _create_ken_burns_clip(img: str, idx: int, tmp: str, resolution: str) -> str:
    preset = random.choice(KEN_BURNS_PRESETS)
    w, h   = (int(v) for v in resolution.split(":"))
    frames = int(IMAGE_DURATION * FPS)
    out    = os.path.join(tmp, f"kb_{idx}.mp4")
    src    = _ensure_reasonable_size(img, tmp)
    _run_ffmpeg([
        "-f", "image2", "-loop", "1", "-i", src,
        "-vf", _zoompan_filter(preset, w, h, frames),
        "-t", str(IMAGE_DURATION),
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
        "-pix_fmt", "yuv420p", "-an", out,
    ])
    return out


def _concat_clips(clips: list, output: str) -> str:
    if len(clips) == 1:
        return clips[0]
    list_file = output + "_list.txt"
    with open(list_file, "w") as f:
        for p in clips:
            f.write(f"file '{os.path.abspath(p)}'\n")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output])
    return output


def _normalize_clip(clip: str, output: str, resolution: str) -> str:
    w, h = resolution.split(":")
    _run_ffmpeg([
        "-i", clip,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
        "-r", "24", "-pix_fmt", "yuv420p", "-an", output,
    ])
    return output


def _overlay_logo(video: str, logo: str, output: str, scale: str, pos: str) -> str:
    w, h = scale.split(":")
    x, y = pos.split(":")
    _run_ffmpeg([
        "-i", video, "-i", logo,
        "-filter_complex", f"[1:v]scale={w}:{h}[logo];[0:v][logo]overlay={x}:{y}",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
        "-pix_fmt", "yuv420p", "-an", output,
    ])
    return output


def _shop_details_clip(img: str, output: str, resolution: str, duration: int) -> str:
    w, h   = resolution.split(":")
    frames = int(duration * FPS)
    _run_ffmpeg([
        "-f", "image2", "-loop", "1", "-i", img,
        "-frames:v", str(frames),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-r", str(FPS), "-c:v", "libx264", "-preset", "ultrafast", "-threads", "4",
        "-pix_fmt", "yuv420p", "-an", output,
    ])
    return output


def _get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error:\n{result.stderr}")
    return float(result.stdout.strip())


def _add_music(video: str, music: str, output: str) -> str:
    duration   = _get_duration(video)
    fade_start = max(duration - 1.5, 0)
    _run_ffmpeg([
        "-i", video, "-i", music,
        "-filter_complex", f"[1:a]atrim=0:{duration},afade=t=out:st={fade_start}:d=1.5[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-shortest", output,
    ])
    return output


# ── Helpers: music + Cloudinary ─────────────────────────────────────────────

from urllib.parse import quote


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


async def _generate_music(duration: float, api_key: str, tmp: str) -> str:
    style        = random.choice(MUSIC_STYLES)
    print(f"[INFO] Music style selected: {style}")
    out          = os.path.join(tmp, "music.mp3")
    duration_int = max(3, int(duration) + 1)
    url          = f"https://gen.pollinations.ai/audio/{quote(style)}"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(
            url,
            params={"model": "acestep", "duration": str(duration_int), "instrumental": "true", "style": style},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
    with open(out, "wb") as f:
        f.write(resp.content)
    return out


async def _upload_video(path: str, cdn_base: str, preset: str) -> str:
    upload_url = cdn_base + "/video/upload"
    with open(path, "rb") as f:
        data = f.read()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            upload_url,
            data={"upload_preset": preset},
            files={"file": (os.path.basename(path), data, "video/mp4")},
        )
        if resp.status_code >= 400:
            print(f"[ERROR] Cloudinary video upload: {resp.text}")
        resp.raise_for_status()
        return resp.json()["secure_url"]
