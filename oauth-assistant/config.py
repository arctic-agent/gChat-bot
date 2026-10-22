"""
Configuration module for User-Delegated OAuth Google Chat Assistant.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent

# Target Space & Credentials
SPACE_NAME = os.getenv("GC_SPACE_NAME", "").strip()
if SPACE_NAME.startswith("space/") and not SPACE_NAME.startswith("spaces/"):
    SPACE_NAME = "spaces/" + SPACE_NAME[6:]
CREDENTIALS_PATH = str(BASE_DIR / os.getenv("CREDENTIALS_FILE", "credentials.json"))
TOKEN_PATH = str(BASE_DIR / os.getenv("TOKEN_FILE", "token.json"))

# Identity & Triggers
BOT_NAME = os.getenv("BOT_NAME", "Team Assistant")
USER_ALIASES = [a.strip().lower() for a in os.getenv("USER_ALIASES", "").split(",") if a.strip()]
BOT_USER_ID = os.getenv("BOT_USER_ID", "").strip()
if BOT_USER_ID and not BOT_USER_ID.startswith("users/"):
    BOT_USER_ID = f"users/{BOT_USER_ID}"
TRIGGER_MODE = os.getenv("TRIGGER_MODE", "smart").lower()
REPLY_IN_THREAD = os.getenv("REPLY_IN_THREAD", "false").lower() in ("true", "1", "yes")

# LLM Configuration
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.fireworks.ai/inference/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "accounts/fireworks/models/minimax-m3")

POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "2.0"))

# Google Drive Integration
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

# Progressive Acknowledgment Message
WAITING_MESSAGE = os.getenv("WAITING_MESSAGE", "⏳ Please wait, let me check and prepare this for you...")


# Google Chat & Drive Scopes required for user delegation
SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
