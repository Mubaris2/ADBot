import uuid
import os
from fastapi import APIRouter, Request
from services.whatsapp import parse_incoming, download_image, send_message
from services.wallet import get_balance, is_balance_sufficient, format_wait_message
from services.background_removal import remove_background, prepare_image_for_video
from services.video_generation import generate_all_videos
from services.video_stitching import finalize_video, upload_to_cloudinary, upload_image_to_cloudinary
from models.job import AdJob, JobStatus
from jobs.scheduler import save_pending_job, run_pipeline
from prompts.scenes import get_unique_scenes
from config import VIDEO_DURATION_SEC, POLLEN_PER_SECOND

router = APIRouter()

# In-memory store per sender: holds uploaded image paths until "make ad" trigger
pending_images: dict[str, list[str]] = {}


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    data = parse_incoming(dict(form))

    sender = data["sender"]

    # ---------- Image upload ----------
    if data["has_images"]:
        if sender not in pending_images:
            pending_images[sender] = []

        for i, url in enumerate(data["media_urls"]):
            count    = len(pending_images[sender])
            filename = f"{sender.replace(':', '_').replace('+', '')}_{count + i}.jpg"
            path     = await download_image(url, filename)
            pending_images[sender].append(path)

        count = len(pending_images[sender])
        send_message(
            sender,
            f"Got it! {count} photo{'s' if count > 1 else ''} received so far.\n"
            f"Send more photos or type *make ad* when ready.",
        )
        return {"status": "images_received"}

    # ---------- Cancel ----------
    if data["is_cancel"]:
        pending_images.pop(sender, None)
        send_message(sender, "Cancelled. Send photos again whenever you are ready.")
        return {"status": "cancelled"}

    # ---------- Trigger ----------
    if data["is_trigger"]:
        images = pending_images.get(sender, [])

        if not images:
            send_message(sender, "No photos found. Please send jewellery photos first.")
            return {"status": "no_images"}

        # Build job
        job = AdJob(
            job_id=str(uuid.uuid4())[:8],
            sender=sender,
            image_paths=images,
        )
        job.calculate_pollen(VIDEO_DURATION_SEC, POLLEN_PER_SECOND)

        # Check wallet
        try:
            balance = await get_balance()
        except Exception:
            send_message(sender, "Could not reach Pollinations wallet. Please try again in a moment.")
            return {"status": "wallet_error"}

        if is_balance_sufficient(balance, job.pollen_required):
            # Enough balance: run immediately
            pending_images.pop(sender, None)
            send_message(sender, f"Creating your ad for {len(images)} jewellery piece{'s' if len(images) > 1 else ''}... Sit tight!")
            await run_pipeline(job)
        else:
            # Low balance: queue and notify
            save_pending_job(job)
            pending_images.pop(sender, None)
            wait_msg = format_wait_message(balance, job.pollen_required, len(images))
            send_message(sender, wait_msg)

        return {"status": "triggered"}

    # ---------- Unknown message ----------
    send_message(
        sender,
        "Send me jewellery photos and type *make ad* when you are ready to create your Instagram ad!",
    )
    return {"status": "unknown"}
