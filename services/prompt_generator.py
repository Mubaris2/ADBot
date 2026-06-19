import asyncio
import time
from google import genai
from google.genai import errors as genai_errors
from config import GEMINI_MODEL, GEMINI_API_KEY

_client = None

# Retry config for transient errors (503 overloaded, 429 rate limited, etc)
MAX_RETRIES = 4
BASE_DELAY_SECONDS = 2


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


SYSTEM_INSTRUCTION = (
    "You write short, vivid AI image-generation prompts for jewellery product photography. "
    "The user will give you a type of jewellery (e.g. 'gold necklace', 'silver earrings'). "
    "Pick ONE random, elegant scene (surface, lighting, props, mood, e.g. velvet cushion, "
    "marble, flowers, soft studio light, golden hour, etc) to use consistently across all "
    "three prompts below, so the three images look like one cohesive shoot. "
    "Then write THREE separate prompts, one per line, each instructing an AI image generator "
    "to take the provided jewellery photo and generate a SINGLE image in that same scene, "
    "while preserving the exact design, color, and details of the original jewellery:\n"
    "Line 1: a front-facing product shot of the jewellery in the scene.\n"
    "Line 2: a close-up detail shot of the jewellery in the scene.\n"
    "Line 3: a styled/worn shot of the jewellery in the scene.\n"
    "Line 4: a short background music style description (genre, instruments, mood, tempo) "
    "that matches the mood of the scene from lines 1-3, suitable for an instrumental "
    "Instagram ad track, under 20 words.\n"
    "STRICT OUTPUT RULES: respond with EXACTLY 4 lines, one item per line, plain text only. "
    "Do NOT use markdown, asterisks, bullet points, numbering, headings, or labels like "
    "'Line 1:'. Do NOT add any preamble, explanation, or quotes. "
    "Each of lines 1-3 should be a single image generation prompt, under 60 words."
)


def _generate_sync(jewellery_type: str) -> list[str]:
    import time
    last_error = None
    for attempt in range(3):
        try:
            response = _get_client().models.generate_content(
                model=GEMINI_MODEL,
                contents=f"Jewellery type: {jewellery_type}",
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "temperature": 1.0,
                    "max_output_tokens": 1024,
                    "thinking_config": {"thinking_budget": 0},
                },
            )
            text = response.text.strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return lines
        except Exception as e:
            last_error = e
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"[WARN] Gemini attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise last_error


async def generate_image_prompts(jewellery_type: str) -> dict:
    """
    Call Gemini to generate 3 separate single-image prompts for the given
    jewellery type, all sharing one randomly chosen scene, plus a matching
    music theme description.
    Returns {"image_prompts": [3 strings], "music_theme": str}
    """
    lines = await asyncio.to_thread(_generate_sync, jewellery_type)

    if len(lines) < 4:
        raise RuntimeError(f"Expected 4 lines, got {len(lines)}: {lines}")

    return {
        "image_prompts": lines[:3],
        "music_theme": lines[3],
    }

