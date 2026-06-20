import uuid
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from services.whatsapp import parse_incoming, download_and_upload_image, send_message, send_video_url
from services.prompt_generator import generate_image_prompts
from services.video_stitching import process_and_upload_video, cleanup_temp

router = APIRouter()

# In-memory per-sender session: Cloudinary image URLs + last music theme
sessions: dict[str, dict] = {}


def _get_session(sender: str) -> dict:
    return sessions.setdefault(sender, {"image_urls": []})


async def _process_images(sender: str, session: dict, media_urls: list) -> None:
    """Download images from Twilio, upload to Cloudinary, store URLs in session."""
    for url in media_urls:
        filename = f"{sender.replace(':', '_').replace('+', '')}_{uuid.uuid4().hex[:8]}.png"
        try:
            cloudinary_url = await download_and_upload_image(url, filename)
            session["image_urls"].append(cloudinary_url)
        except Exception as e:
            print(f"[ERROR] Failed to process image from {url}: {e}")
            send_message(sender, f"Failed to save one image. Please try sending it again.\nError: {str(e)[:200]}")
            return

    count = len(session["image_urls"])
    send_message(
        sender,
        f"Got it! {count} image{'s' if count > 1 else ''} collected so far.\n"
        f"Send more, send a jewellery type for a new prompt, or type *make ad* when ready.",
    )


async def _process_make_ad(sender: str, session: dict) -> None:
    """Trigger Modal video pipeline with collected Cloudinary image URLs."""
    image_urls = session["image_urls"]

    if not image_urls:
        send_message(
            sender,
            "No images collected yet. Send a jewellery type to get a prompt, "
            "generate images, and send them here first.",
        )
        return

    send_message(sender, "Creating your ad... this may take a minute!")

    try:
        public_url = await process_and_upload_video(
            image_urls=image_urls,
        )

        send_video_url(
            sender,
            public_url,
            caption="Your jewellery ad is ready! Save and post on Instagram.",
        )

        cleanup_temp()

    except Exception as e:
        print(f"[ERROR] _process_make_ad failed for {sender}:\n{str(e)}")
        send_message(sender, f"Something went wrong while creating your ad.\nError: {str(e)[:300]}")

    session["image_urls"] = []


async def _process_jewellery_type(sender: str, session: dict, jewellery_type: str) -> None:
    try:
        result = await generate_image_prompts(jewellery_type)
    except Exception as e:
        print(f"[ERROR] _process_jewellery_type failed for {sender}:\n{str(e)}")
        send_message(sender, f"Could not generate a prompt right now. Please try again.\nError: {str(e)[:300]}")
        return

    prompts     = result["image_prompts"]

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
        session["image_urls"] = []
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
