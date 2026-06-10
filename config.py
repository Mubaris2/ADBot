import os
from dotenv import load_dotenv

load_dotenv()

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # e.g. whatsapp:+14155238886

# Pollinations
POLLINATIONS_API_URL = "https://gen.pollinations.ai"
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")

# Wallet
POLLEN_PER_SECOND = 0.005        # LTX-2 cost per second
POLLEN_PER_HOUR   = 0.01         # Free replenishment rate
VIDEO_DURATION_SEC = 7           # Seconds per jewellery clip
WALLET_POLL_INTERVAL_MIN = 30    # How often scheduler checks balance

# Video
SHOP_LOGO_PATH         = "assets/shop_logo.png"
SHOP_DETAILS_PATH      = "assets/shop_details.jpg"
SHOP_DETAILS_DURATION  = 4       # Seconds for final shop card
LOGO_POSITION          = "10:10" # top-left corner (x:y)
LOGO_SCALE             = "80:80" # width:height in pixels
OUTPUT_RESOLUTION      = "720:1280"  # 9:16 vertical for Instagram

# Temp
TEMP_DIR = "temp"
