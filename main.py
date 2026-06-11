from fastapi import FastAPI
from contextlib import asynccontextmanager
from routes.webhook import router as webhook_router
from jobs.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Jewellery Ad Bot",
    description="WhatsApp bot that turns jewellery photos into Instagram video ads.",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/health")
def health():
    return {"status": "ok"}
