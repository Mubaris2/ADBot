import random

SCENE_PROMPTS = [
    "elegant jewellery placed on smooth black marble with soft studio lighting",
    "gold jewellery resting on pink velvet cushion with bokeh background",
    "ornament displayed on white silk cloth near a sunlit window",
    "jewellery on mossy stone beside a gentle waterfall, natural light",
    "piece placed on dried flowers and petals, warm golden hour light",
    "jewellery on dark wooden surface with candles glowing softly nearby",
    "ornament resting on colourful silk fabric in vibrant studio setting",
    "jewellery on frosted glass with subtle blue ambient light",
    "piece displayed on rustic terracotta tile with green leaves around",
    "jewellery on white sand with soft ocean light in background",
    "ornament on plush red velvet in luxury jewellery box setting",
    "piece on polished copper tray with warm candlelight atmosphere",
]


def get_random_scene(exclude: list = None) -> str:
    """Pick a random scene prompt, optionally excluding recently used ones."""
    pool = SCENE_PROMPTS
    if exclude:
        pool = [p for p in SCENE_PROMPTS if p not in exclude]
        if not pool:
            pool = SCENE_PROMPTS  # fallback if all excluded
    return random.choice(pool)


def get_unique_scenes(count: int) -> list:
    """Get a list of unique scene prompts for multiple images."""
    if count >= len(SCENE_PROMPTS):
        return random.sample(SCENE_PROMPTS, len(SCENE_PROMPTS)) + \
               random.choices(SCENE_PROMPTS, k=count - len(SCENE_PROMPTS))
    return random.sample(SCENE_PROMPTS, count)
