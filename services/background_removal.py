import os
from PIL import Image
from rembg import remove, new_session
from config import TEMP_DIR

# Reuse session across calls for performance
_session = new_session("u2net")


def remove_background(image_path: str) -> str:
    """
    Remove background from a jewellery image.
    Returns path to the new PNG with transparent background.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    filename   = os.path.splitext(os.path.basename(image_path))[0]
    output_path = os.path.join(TEMP_DIR, f"{filename}_nobg.png")

    with open(image_path, "rb") as f:
        input_data = f.read()

    output_data = remove(input_data, session=_session)

    with open(output_path, "wb") as f:
        f.write(output_data)

    return output_path


def prepare_image_for_video(nobg_path: str, width: int = 720, height: int = 1280) -> str:
    """
    Compose the transparent jewellery cutout onto a white canvas,
    centered and scaled to fit. This gives LTX-2 a clean input image.
    Returns path to the composited PNG.
    """
    filename    = os.path.splitext(os.path.basename(nobg_path))[0]
    output_path = os.path.join(TEMP_DIR, f"{filename}_ready.png")

    jewellery = Image.open(nobg_path).convert("RGBA")

    # Scale jewellery to fit 60% of canvas, preserve aspect ratio
    max_w = int(width  * 0.6)
    max_h = int(height * 0.6)
    jewellery.thumbnail((max_w, max_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))

    # Center paste
    x = (width  - jewellery.width)  // 2
    y = (height - jewellery.height) // 2
    canvas.paste(jewellery, (x, y), jewellery)

    canvas.convert("RGB").save(output_path, "PNG")
    return output_path
