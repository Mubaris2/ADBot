import os
import uuid
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from services.whatsapp import parse_incoming, download_image, send_message, send_video_url
from services.prompt_generator import generate_image_prompts
from services.ken_burns import create_ornament_clip
from services.video_stitching import finalize_video, upload_to_cloudinary, cleanup_temp
from services.music_generation import generate_music

router = APIRouter()

# In-memory per-sender session: collected images + last music theme
sessions: dict[str, dict] = {}


def _get_session(sender: str) -> dict:
    return sessions.setdefault(sender, {"images": [], "music_theme": None})


async def _process_images(sender: str, session: dict, media_urls: list) -> None:
    for url in media_urls:
        filename = f"{sender.replace(':', '_').replace('+', '')}_{uuid.uuid4().hex[:8]}.png"
        path     = await download_image(url, filename)
        session["images"].append(path)

    count = len(session["images"])
    send_message(
        sender,
        f"Got it! {count} image{'s' if count > 1 else ''} collected so far.\n"
        f"Send more, send a jewellery type for a new prompt, or type *make ad* when ready.",
    )


async def _process_make_ad(sender: str, session: dict) -> None:
    images = session["images"]

    if not images:
        send_message(
            sender,
            "No images collected yet. Send a jewellery type to get a prompt, "
            "generate images, and send them here first.",
        )
        return

    send_message(sender, "Creating your ad... this may take a minute!")

    music_theme = session.get("music_theme")

    async def music_fn(duration: float) -> str:
        return await generate_music(duration=duration, style=music_theme)

    try:
        create_ornament_clip(images, ornament_index=0)

        final_path = await finalize_video(job_id="latest", generate_music_fn=music_fn)
        public_url = await upload_to_cloudinary(final_path)

        send_video_url(
            sender,
            public_url,
            caption="Your jewellery ad is ready! Save and post on Instagram.",
        )

        cleanup_temp(keep=["shop_details.jpg"])

    except Exception as e:
        send_message(sender, f"Something went wrong while creating your ad.\nError: {str(e)}")

    session["images"] = []


async def _process_jewellery_type(sender: str, session: dict, jewellery_type: str) -> None:
    try:
        result = await generate_image_prompts(jewellery_type)
    except Exception as e:
        send_message(sender, f"Could not generate a prompt right now. Please try again.\nError: {str(e)}")
        return

    prompts     = result["image_prompts"]
    music_theme = result["music_theme"]

    session["music_theme"] = music_theme

    prompts_text = "\n\n".join(
        f"Image {i + 1}:\n{p}" for i, p in enumerate(prompts)
    )

    send_message(
        sender,
        f"Here are your prompts:\n\n{prompts_text}\n\n"
        f"Generate each image using its prompt, then send all images back here.\n"
        f"Type *make ad* once you've sent all images.",
    )


@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    data = parse_incoming(dict(form))

    sender  = data["sender"]
    session = _get_session(sender)

    # ---------- Image upload ----------
    if data["has_images"]:
        background_tasks.add_task(_process_images, sender, session, data["media_urls"])
        return Response(status_code=200)

    # ---------- Cancel ----------
    if data["is_cancel"]:
        session["images"] = []
        send_message(sender, "Cleared collected images. Send a jewellery type or new images anytime.")
        return Response(status_code=200)

    # ---------- "make ad" ----------
    if data["is_trigger"]:
        background_tasks.add_task(_process_make_ad, sender, session)
        return Response(status_code=200)

    # ---------- Plain text: jewellery type ----------
    if data["body"]:
        background_tasks.add_task(_process_jewellery_type, sender, session, data["body"])
        return Response(status_code=200)

    # ---------- Fallback ----------
    send_message(
        sender,
        "Send me the jewellery type (e.g. 'gold necklace') to get a prompt, "
        "or send images and type *make ad*.",
    )
    return Response(status_code=200)
