import asyncio
from google import genai
from config import GEMINI_MODEL, GEMINI_API_KEY

_client = None


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
    "STRICT OUTPUT RULES: respond with EXACTLY 3 lines, one prompt per line, plain text only. "
    "Do NOT use markdown, asterisks, bullet points, numbering, headings, or labels like "
    "'Line 1:'. Do NOT add any preamble, explanation, or quotes. "
    "Each line should be a single image generation prompt, under 60 words."
)


def _generate_sync(jewellery_type: str) -> list[str]:
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


async def generate_image_prompts(jewellery_type: str) -> list[str]:
    """
    Call Gemini to generate 3 separate single-image prompts for the given
    jewellery type, all sharing one randomly chosen scene.
    Returns a list of 3 prompt strings (front, close-up, styled).
    """
    lines = await asyncio.to_thread(_generate_sync, jewellery_type)

    if len(lines) < 3:
        raise RuntimeError(f"Expected 3 prompt lines, got {len(lines)}: {lines}")

    return lines[:3]

