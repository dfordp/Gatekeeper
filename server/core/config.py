# server/core/config.py
"""Configuration and environment loading"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== DATABASE ====================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gatekeeper_user:gatekeeper_secure_password_123@localhost:5432/gatekeeper_db"
)

# ==================== JWT CONFIGURATION ====================
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-key-change-in-production-12345")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 8

# ==================== ADMIN CONFIGURATION ====================
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "admin-secret-key-change-in-production-67890")

# ==================== EXTERNAL SERVICES ====================
# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_TOKEN = TELEGRAM_BOT_TOKEN  # Alias for compatibility
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# Groq AI
# In server/core/config.py, update the vision model line:

# Groq AI
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant-on_demand")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Cloudinary (for Phase 5)
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

# WhatsApp (for Phase 7)
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")

# ==================== APP CONFIGURATION ====================
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = os.getenv("APP_DEBUG", "False").lower() == "true"

# ==================== CORS CONFIGURATION ====================
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

# ==================== REDIS CACHE CONFIGURATION ====================
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "True").lower() == "true"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
CACHE_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "60"))  # seconds
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))  # max entries