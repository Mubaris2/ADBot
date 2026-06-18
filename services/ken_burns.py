import subprocess
import os
import random
from PIL import Image
from config import TEMP_DIR, OUTPUT_RESOLUTION

# Frame rate for all clips
FPS = 30

# Per-image duration before crossfade overlap
IMAGE_DURATION = 2.7

# Crossfade duration between images
CROSSFADE_DURATION = 0.5

KEN_BURNS_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal"]


def _ensure_reasonable_size(image_path: str, max_dimension: int = 1600) -> str:
    """
    Downscale an image if it's larger than necessary before handing it to
    FFmpeg, to avoid memory spikes decoding very large source photos
    (e.g. modern phone camera images can be 3000px+).
    """
    with Image.open(image_path) as img:
        if max(img.size) <= max_dimension:
            return image_path

        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
        resized_path = os.path.join(
            TEMP_DIR, f"resized_{os.path.basename(image_path)}"
        )
        os.makedirs(TEMP_DIR, exist_ok=True)
        img.convert("RGB").save(resized_path, "PNG")
        return resized_path


def _run_ffmpeg(args: list) -> None:
    cmd = ["ffmpeg", "-y", "-nostdin"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")


def _zoompan_filter(preset: str, width: int, height: int, total_frames: int) -> str:
    """
    Build the zoompan filter string for a given preset.
    Image is first scaled up so pan/zoom has room to move without showing edges.
    """
    # Scale source up 1.3x so panning doesn't reveal empty edges
    scale_w = int(width * 1.3)
    scale_h = int(height * 1.3)

    z_expr = "1.0"
    x_expr = f"(iw-ow)/2"
    y_expr = f"(ih-oh)/2"

    if preset == "zoom_in":
        z_expr = f"min(zoom+0.0015,1.2)"
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2"
    elif preset == "zoom_out":
        z_expr = f"if(eq(on,0),1.2,max(zoom-0.0015,1.0))"
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2"
    elif preset == "pan_left":
        z_expr = "1.1"
        x_expr = f"(iw-ow)*(1-on/{total_frames})"
        y_expr = "(ih-oh)/2"
    elif preset == "pan_right":
        z_expr = "1.1"
        x_expr = f"(iw-ow)*(on/{total_frames})"
        y_expr = "(ih-oh)/2"
    elif preset == "diagonal":
        z_expr = f"min(zoom+0.001,1.15)"
        x_expr = f"(iw-ow)*(on/{total_frames})"
        y_expr = f"(ih-oh)*(on/{total_frames})"

    return (
        f"scale={scale_w}:{scale_h},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={FPS}"
    )


def create_ken_burns_clip(image_path: str, index: int, preset: str = None) -> str:
    """
    Create a short video clip from a single image with Ken Burns motion.
    If preset is None, picks one randomly.
    """
    if preset is None:
        preset = random.choice(KEN_BURNS_PRESETS)

    w, h = OUTPUT_RESOLUTION.split(":")
    w, h = int(w), int(h)
    total_frames = int(IMAGE_DURATION * FPS)

    output = os.path.join(TEMP_DIR, f"kb_{index}.mp4")
    vf = _zoompan_filter(preset, w, h, total_frames)

    source_path = _ensure_reasonable_size(image_path)

    _run_ffmpeg([
        "-f", "image2",
        "-loop", "1",
        "-i", source_path,
        "-vf", vf,
        "-t", str(IMAGE_DURATION),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        output,
    ])
    return output


def concat_clips(clip_paths: list, output_name: str) -> str:
    """
    Concatenate clips back-to-back (hard cuts) using the concat demuxer.
    Reliable for any number of clips, unlike chained xfade.
    """
    if len(clip_paths) == 1:
        return clip_paths[0]

    output    = os.path.join(TEMP_DIR, output_name)
    list_file = os.path.join(TEMP_DIR, f"{output_name}_list.txt")

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


def create_ornament_clip(image_paths: list, ornament_index: int) -> str:
    """
    Full pipeline for one ornament:
    1. Apply random Ken Burns effect to each of the (typically 3) images
    2. Crossfade them together into a single ~7s clip
    Returns path to the clip, named clip_XX.mp4 for downstream stitching.
    """
    kb_clips = [
        create_ken_burns_clip(path, index=f"{ornament_index}_{i}")
        for i, path in enumerate(image_paths)
    ]

    merged = concat_clips(kb_clips, output_name=f"ornament_{ornament_index:02d}.mp4")

    # Rename to match naming expected by video_stitching.finalize_video
    final_output = os.path.join(TEMP_DIR, f"clip_{ornament_index:02d}.mp4")
    if merged != final_output:
        os.replace(merged, final_output)

    return final_output
