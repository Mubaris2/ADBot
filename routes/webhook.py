import os
import uuid
from fastapi import APIRouter, Request
from services.whatsapp import parse_incoming, download_image, send_message, send_video_url
from services.prompt_generator import generate_image_prompts
from services.ken_burns import create_ornament_clip
from services.video_stitching import finalize_video, upload_to_cloudinary

router = APIRouter()

# In-memory per-sender session state
# state: "idle" | "awaiting_images"
sessions: dict[str, dict] = {}


def _get_session(sender: str) -> dict:
    if sender not in sessions:
        sessions[sender] = {"state": "idle", "images": []}
    return sessions[sender]


def _reset_session(sender: str) -> None:
    sessions[sender] = {"state": "idle", "images": []}


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    data = parse_incoming(dict(form))

    sender  = data["sender"]
    session = _get_session(sender)

    # ---------- Image upload (only matters in awaiting_images state) ----------
    if data["has_images"]:
        if session["state"] != "awaiting_images":
            send_message(
                sender,
                "Please send the jewellery type first (e.g. 'gold necklace') "
                "so I can give you a prompt before sending images.",
            )
            return {"status": "ignored_image"}

        for url in data["media_urls"]:
            filename = f"{sender.replace(':', '_').replace('+', '')}_{uuid.uuid4().hex[:8]}.png"
            path     = await download_image(url, filename)
            session["images"].append(path)

        count = len(session["images"])
        send_message(
            sender,
            f"Got it! {count} image{'s' if count > 1 else ''} received.\n"
            f"Send more, or type *make ad* when ready.",
        )
        return {"status": "images_received"}

    # ---------- Cancel ----------
    if data["is_cancel"]:
        _reset_session(sender)
        send_message(sender, "Cancelled. Send a jewellery type whenever you're ready to start again.")
        return {"status": "cancelled"}

    # ---------- "make ad" trigger ----------
    if data["is_trigger"]:
        if session["state"] != "awaiting_images" or not session["images"]:
            send_message(
                sender,
                "No images to work with yet. Send a jewellery type first, "
                "then send the generated images.",
            )
            return {"status": "no_images"}

        send_message(sender, "Creating your ad... this may take a minute!")

        print(f"[DEBUG] session images for {sender}: {session['images']}")
        for p in session["images"]:
            print(f"[DEBUG]   {p} exists={os.path.exists(p)} size={os.path.getsize(p) if os.path.exists(p) else 'N/A'}")

        try:
            create_ornament_clip(session["images"], ornament_index=0)
            final_path = finalize_video(job_id="latest")
            public_url = await upload_to_cloudinary(final_path)

            send_video_url(
                sender,
                public_url,
                caption="Your jewellery ad is ready! Save and post on Instagram.",
            )
        except Exception as e:
            send_message(sender, f"Something went wrong while creating your ad.\nError: {str(e)}")

        _reset_session(sender)
        return {"status": "done"}

    # ---------- Jewellery type (idle state, plain text) ----------
    if session["state"] == "idle" and data["body"]:
        jewellery_type = data["body"]

        try:
            prompts = await generate_image_prompts(jewellery_type)
        except Exception as e:
            send_message(sender, f"Could not generate a prompt right now. Please try again.\nError: {str(e)}")
            return {"status": "prompt_error"}

        session["state"]  = "awaiting_images"
        session["images"] = []

        prompts_text = "\n\n".join(
            f"Image {i + 1}:\n{p}" for i, p in enumerate(prompts)
        )

        send_message(
            sender,
            f"Here are your prompts:\n\n{prompts_text}\n\n"
            f"Generate each image using its prompt, then send all images back here.\n"
            f"Type *make ad* once you've sent all images.",
        )
        return {"status": "prompt_sent"}

    # ---------- Fallback ----------
    send_message(
        sender,
        "Send me the jewellery type (e.g. 'gold necklace') to get started!",
    )
    return {"status": "unknown"}
