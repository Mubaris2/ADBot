from fastapi import FastAPI
from routes.webhook import router as webhook_router

app = FastAPI(
    title="Jewellery Ad Bot",
    description="WhatsApp bot that turns AI-generated jewellery photos into Instagram video ads.",
)

app.include_router(webhook_router)


@app.get("/health")
def health():
    return {"status": "ok"}
