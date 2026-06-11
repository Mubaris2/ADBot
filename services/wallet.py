import httpx
import math
from config import (
    POLLINATIONS_API_URL,
    POLLINATIONS_API_KEY,
    POLLEN_PER_HOUR,
)


async def get_balance() -> float:
    """Fetch current pollen wallet balance from Pollinations API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POLLINATIONS_API_URL}/account/balance",
            headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"},
        )
        response.raise_for_status()
        data = response.json()
        return float(data.get("balance", 0.0))


def is_balance_sufficient(balance: float, required: float) -> bool:
    return balance >= required


def estimate_wait_minutes(balance: float, required: float) -> int:
    """How many minutes until wallet has enough pollen."""
    shortfall = required - balance
    hours_needed = shortfall / POLLEN_PER_HOUR
    minutes = math.ceil(hours_needed * 60)
    return minutes


def format_wait_message(balance: float, required: float, num_images: int) -> str:
    minutes = estimate_wait_minutes(balance, required)
    hours = minutes // 60
    mins = minutes % 60

    if hours > 0:
        time_str = f"{hours} hour{'s' if hours > 1 else ''} {mins} min" if mins else f"{hours} hour{'s' if hours > 1 else ''}"
    else:
        time_str = f"{mins} minute{'s' if mins > 1 else ''}"

    return (
        f"Wallet is a little low right now.\n\n"
        f"Balance: {balance:.4f} pollen\n"
        f"Needed for {num_images} jewellery video{'s' if num_images > 1 else ''}: {required:.4f} pollen\n\n"
        f"Wallet refills automatically. Your ad will be ready in about *{time_str}*.\n"
        f"I will send it to you as soon as it is done, no need to do anything!"
    )
