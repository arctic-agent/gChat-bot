"""
Messenger module for sending messages via Google Chat Incoming Webhook.
"""

import logging
import os
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger("webhook-messenger")

WEBHOOK_URL = os.getenv("CHAT_WEBHOOK_URL", "")


def send_webhook_message(
    text: str,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Send a message to Google Chat via Incoming Webhook.
    
    If thread_key is None, posts as a brand-new top-level message.
    If thread_key is provided, replies inside that thread.
    """
    url = webhook_url or WEBHOOK_URL
    if not url:
        logger.error("No CHAT_WEBHOOK_URL configured!")
        return False

    params = {}
    payload = {"text": text}

    if thread_key:
        params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
        if thread_key.startswith("spaces/"):
            thread_id = thread_key.split("/")[-1]
            payload["thread"] = {"name": thread_key, "threadKey": thread_id}
        else:
            payload["thread"] = {"threadKey": thread_key}

    try:
        response = requests.post(url, params=params, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Message sent successfully via webhook!")
            return True
        else:
            logger.error("Webhook error (%d): %s", response.status_code, response.text)
            return False
    except Exception:
        logger.exception("Failed to send message via webhook.")
        return False
