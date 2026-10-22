"""
Configuration module for Webhook Google Chat Assistant.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent

# Target Space & Webhook
SPACE_NAME = os.getenv("GC_SPACE_NAME", "").strip()
if SPACE_NAME.startswith("space/") and not SPACE_NAME.startswith("spaces/"):
    SPACE_NAME = "spaces/" + SPACE_NAME[6:]
WEBHOOK_URL = os.getenv("CHAT_WEBHOOK_URL", "")

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

# Optional Pub/Sub Monitoring
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
SUBSCRIPTION_ID = os.getenv("PUBSUB_SUBSCRIPTION_ID", "")
SUBSCRIPTION_PATH = f"projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}" if PROJECT_ID and SUBSCRIPTION_ID else ""
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "2.0"))

# Credential Paths
TOKEN_PATH = str(BASE_DIR / os.getenv("TOKEN_FILE", "token.json"))
SA_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if SA_KEY_PATH and not os.path.isabs(SA_KEY_PATH):
    SA_KEY_PATH = str(BASE_DIR / SA_KEY_PATH)

# Google Drive Integration
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

# Progressive Acknowledgment Message
WAITING_MESSAGE = os.getenv("WAITING_MESSAGE", "⏳ Please wait, let me check and prepare this for you...")

