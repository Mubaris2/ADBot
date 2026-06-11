import asyncio
import json
import os
import sqlite3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from models.job import AdJob, JobStatus
from config import WALLET_POLL_INTERVAL_MIN, VIDEO_DURATION_SEC, POLLEN_PER_SECOND
from services.wallet import get_balance, is_balance_sufficient
from services.whatsapp import send_message, send_video_url
from services.background_removal import remove_background, prepare_image_for_video
from services.video_generation import generate_all_videos
from services.video_stitching import finalize_video, upload_to_cloudinary, upload_image_to_cloudinary
from prompts.scenes import get_unique_scenes

DB_PATH = "db/jobs.db"

scheduler = AsyncIOScheduler()


# ---------- DB helpers ----------

def init_db() -> None:
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_jobs (
            job_id      TEXT PRIMARY KEY,
            sender      TEXT NOT NULL,
            image_paths TEXT NOT NULL,
            pollen_req  REAL NOT NULL,
            created_at  REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_pending_job(job: AdJob) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO pending_jobs VALUES (?, ?, ?, ?, ?)",
        (
            job.job_id,
            job.sender,
            json.dumps(job.image_paths),
            job.pollen_required,
            job.created_at,
        ),
    )
    conn.commit()
    conn.close()


def load_pending_jobs() -> list[AdJob]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM pending_jobs").fetchall()
    conn.close()

    jobs = []
    for row in rows:
        job = AdJob(
            job_id=row[0],
            sender=row[1],
            image_paths=json.loads(row[2]),
            pollen_required=row[3],
            created_at=row[4],
            status=JobStatus.PENDING,
        )
        jobs.append(job)
    return jobs


def delete_pending_job(job_id: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM pending_jobs WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()


# ---------- Pipeline ----------

async def run_pipeline(job: AdJob) -> None:
    """Full ad creation pipeline for one job."""
    try:
        send_message(job.sender, "Your wallet is topped up! Starting your ad now...")

        # BG removal + prepare
        prepared = []
        for path in job.image_paths:
            nobg    = remove_background(path)
            ready   = prepare_image_for_video(nobg)
            prepared.append(ready)

        # Upload prepared images so LTX-2 can fetch them via URL
        prepared_urls = [await upload_image_to_cloudinary(p) for p in prepared]

        # Scene prompts
        scenes = get_unique_scenes(len(prepared_urls))

        # Generate video clips
        await generate_all_videos(prepared_urls, scenes)

        # Stitch final video
        final_path = finalize_video(job.job_id)

        # Upload to Cloudinary
        public_url = await upload_to_cloudinary(final_path)

        # Send to dad
        send_video_url(
            job.sender,
            public_url,
            caption="Your jewellery ad is ready! Save and post on Instagram.",
        )

    except Exception as e:
        send_message(
            job.sender,
            f"Something went wrong while creating your ad. Please try again.\nError: {str(e)}",
        )
        raise


# ---------- Scheduler job ----------

async def check_pending_jobs() -> None:
    """
    Runs every WALLET_POLL_INTERVAL_MIN minutes.
    Checks wallet balance and runs any jobs that can now be fulfilled.
    """
    jobs = load_pending_jobs()
    if not jobs:
        return

    try:
        balance = await get_balance()
    except Exception:
        return  # API unreachable, try again next cycle

    for job in jobs:
        if is_balance_sufficient(balance, job.pollen_required):
            delete_pending_job(job.job_id)
            balance -= job.pollen_required  # optimistic deduct for next iteration
            asyncio.create_task(run_pipeline(job))


def start_scheduler() -> None:
    init_db()
    scheduler.add_job(
        check_pending_jobs,
        trigger="interval",
        minutes=WALLET_POLL_INTERVAL_MIN,
        id="wallet_poll",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
