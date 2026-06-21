# ADBot : WhatsApp Jewellery Ad Generator

A WhatsApp bot that helps jewellery shop owners create Instagram video ads by simply chatting. Send a jewellery type, get AI image prompts, send back the generated images, and receive a ready-to-post video ad with Ken Burns motion effects and background music.

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Twilio-F22F46?style=flat-square&logo=twilio&logoColor=white" />
  <img src="https://img.shields.io/badge/Google%20Gemini-4285F4?style=flat-square&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/FFmpeg-007808?style=flat-square&logo=ffmpeg&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloudinary-3448C5?style=flat-square&logo=cloudinary&logoColor=white" />
  <img src="https://img.shields.io/badge/Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white" />
</p>

---

## How It Works

```
User: "gold necklace"
Bot : 3 image prompts (front / close-up / styled)
User: generates images externally, sends back 3 photos
Bot : "Got it! 3 images collected."
User: "make ad"
Bot : "Creating your ad..." → video with music → sent back on WhatsApp
```

### Keywords
| Keyword | Action |
|---|---|
| Any text | Treated as jewellery type, generates 3 image prompts |
| Send images | Collected and uploaded to Cloudinary |
| `make ad` | Triggers video generation |
| `cancel` | Clears collected images |

---

## Architecture

```
WhatsApp → Twilio → Railway (webhook)
                         │
                         ├── Gemini API (image prompt generation)
                         ├── Cloudinary (image storage)
                         │
                         └── Modal (FFmpeg video processing)
                                  │
                                  ├── Ken Burns clips per image
                                  ├── Logo watermark overlay
                                  ├── Shop details card
                                  ├── Pollinations AI music
                                  └── Cloudinary (final video upload)
```

**Railway** handles the WhatsApp webhook, session state, prompt generation, and image collection. All heavy FFmpeg video processing is offloaded to **Modal** serverless infrastructure to avoid memory and CPU limits.

---

## Stack

| Layer | Tool |
|---|---|
| Bot interface | Twilio WhatsApp Sandbox |
| Backend | Python FastAPI + Uvicorn |
| Prompt generation | Gemini (`gemini-3.1-flash-lite`) via `google-genai` |
| Video processing | Modal (serverless, 4 vCPU / 2GB RAM) |
| Video effects | FFmpeg (Ken Burns zoompan + concat) |
| Music | Pollinations `acestep` model |
| File storage | Cloudinary (images + final video) |
| Deployment | Railway (Hobby tier) |

---

## File Structure

```
ADBot/
├── main.py
├── config.py
├── Dockerfile
├── requirements.txt
├── .env.example
├── modal_processor.py        # Deploy to Modal separately
├── assets/
│   ├── shop_logo.png         # Watermark (add manually)
│   └── shop_details.png      # Final card (add manually)
├── temp/                     # Auto-cleaned after each run
├── routes/
│   └── webhook.py            # Twilio POST /webhook handler
└── services/
    ├── whatsapp.py           # Twilio send/receive + Cloudinary image upload
    ├── prompt_generator.py   # Gemini: 3 image prompts
    ├── video_stitching.py    # Calls Modal endpoint, returns video URL
    └── music_generation.py   # Pollinations: AI background music (Railway side, unused in prod)
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Mubaris2/ADBot.git
cd ADBot
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_WHATSAPP_NUMBER` | e.g. `whatsapp:+14155238886` |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `POLLINATIONS_API_KEY` | Pollinations API key |
| `CLOUDINARY_BASE_URL` | `https://api.cloudinary.com/v1_1/<cloud_name>` |
| `CLOUDINARY_UPLOAD_PRESET` | Unsigned upload preset name |
| `MODAL_ENDPOINT_URL` | Set after Modal deploy (see below) |

### 3. Add assets

Place these two files in the `assets/` folder:
- `shop_logo.png` — watermark shown on jewellery clips
- `shop_details.png` — final 4-second card shown at the end of the ad

### 4. Set up Cloudinary

- Create an **unsigned upload preset** in Cloudinary dashboard
- The same preset is used for both image and video uploads
- The bot appends `/image/upload` or `/video/upload` to `CLOUDINARY_BASE_URL` automatically

### 5. Deploy Modal processor

Install Modal and authenticate:

```bash
pip install modal
modal setup
```

Create Modal secrets (one-time):

```bash
modal secret create jewellery-ad-secrets \
  CLOUDINARY_BASE_URL=https://api.cloudinary.com/v1_1/<cloud_name> \
  CLOUDINARY_UPLOAD_PRESET=your_preset \
  POLLINATIONS_API_KEY=your_key
```

Deploy:

```bash
modal deploy modal_processor.py
```

Copy the printed endpoint URL and set it as `MODAL_ENDPOINT_URL` in Railway.

### 6. Deploy to Railway

- Push repo to GitHub
- Create a new Railway project, connect the repo
- Add all `.env` variables in Railway dashboard
- Railway auto-deploys via `Dockerfile`

### 7. Configure Twilio webhook

Set your Railway app URL as the Twilio WhatsApp webhook:

```
https://<your-railway-domain>/webhook
```

Method: `POST`

---

## Video Pipeline (on Modal)

1. Download jewellery images from Cloudinary
2. Resize each image to max 768px (memory protection)
3. Apply random Ken Burns effect per image (zoom in/out, pan left/right, diagonal)
4. Concatenate clips with hard cuts
5. Normalize to `720x1280` (9:16 for Instagram)
6. Overlay shop logo on jewellery section
7. Append shop details card (4 seconds, no logo)
8. Generate AI background music via Pollinations and overlay with 1.5s fade-out
9. Upload final video to Cloudinary and return public URL

---

## Known Quirks

- Railway logs show all uvicorn `INFO` lines as `severity: error` — this is a Railway cosmetic bug, not real errors
- Modal container has a cold start of ~3-5s if idle; negligible for this use case
- Twilio MMS images sometimes return 404 immediately after webhook fires — the bot retries up to 5 times with exponential backoff
- Gemini 503 errors on Railway IPs are handled with 3-retry exponential backoff

---

## Local Development

```bash
uvicorn main:app --reload --port 8000
```

Use [ngrok](https://ngrok.com) to expose localhost to Twilio:

```bash
ngrok http 8000
```

Set the ngrok URL as your Twilio webhook during local testing.