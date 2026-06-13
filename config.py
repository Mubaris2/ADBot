import os
from dotenv import load_dotenv

load_dotenv()

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # e.g. whatsapp:+14155238886

# Gemini (for image prompt generation)
GEMINI_MODEL   = "gemini-3.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Cloudinary
CLOUDINARY_UPLOAD_URL    = os.getenv("CLOUDINARY_UPLOAD_URL")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET")

# Video
SHOP_LOGO_PATH         = "assets/shop_logo.png"
SHOP_DETAILS_PATH      = "assets/shop_details.jpg"
SHOP_DETAILS_DURATION  = 3       # Seconds for final shop card
LOGO_POSITION          = "10:10" # top-left corner (x:y)
LOGO_SCALE             = "80:80" # width:height in pixels
OUTPUT_RESOLUTION      = "720:1280"  # 9:16 vertical for Instagram

# Temp
TEMP_DIR = "temp"
