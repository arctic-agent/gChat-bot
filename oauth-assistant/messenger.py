"""
Messenger module for sending messages via User-Delegated OAuth.
Works in ANY space, group, or DM the authenticated user belongs to.
"""

import logging
from typing import Optional
import requests

import auth
import config

logger = logging.getLogger("oauth-messenger")


def send_user_message(
    space_name: str,
    text: str,
    thread_name: Optional[str] = None,
    token_path: Optional[str] = None,
) -> bool:
    """
    Send a message to Google Chat on behalf of the authenticated user.
    Displays in chat as: [User Name] [GCP Chat App Name]
    """
    creds = auth.get_valid_credentials(token_path or config.TOKEN_PATH)
    if not creds:
        logger.error("No valid OAuth credentials found. Run auth.py first!")
        return False

    url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    params = {}

    if thread_name:
        payload["thread"] = {"name": thread_name}
        params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

    try:
        res = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
        if res.status_code in (200, 201):
            logger.info("Message sent successfully via User OAuth to %s!", space_name)
            return True
        else:
            logger.error("User OAuth send error (%d): %s", res.status_code, res.text)
            return False
    except Exception:
        logger.exception("Failed to send message via User OAuth.")
        return False
