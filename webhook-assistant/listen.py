"""
Real-time Google Chat Space Listener for Webhook Assistant.
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import agent
import config

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("webhook-listener")

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
]

token_lock = threading.Lock()
process_lock = threading.Lock()
stop_event = threading.Event()
# Tracks message ID -> {"update_time": str, "text_hash": str}
processed_messages: dict = {}
executor = ThreadPoolExecutor(max_workers=20)


def hash_content(text: str) -> str:
    import hashlib
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def get_access_token() -> Optional[str]:
    # Check config.TOKEN_PATH, then fall back to sibling oauth-assistant/token.json
    candidate_paths = [
        config.TOKEN_PATH,
        str(config.BASE_DIR / "token.json"),
        str(config.BASE_DIR.parent / "oauth-assistant" / "token.json"),
    ]
    resolved_path = None
    for p in candidate_paths:
        if p and os.path.exists(p):
            resolved_path = p
            break

    if not resolved_path:
        return None

    with token_lock:
        try:
            creds = Credentials.from_authorized_user_file(resolved_path, SCOPES)
        except Exception as e:
            logger.error("Failed to parse token file %s: %s", resolved_path, e)
            return None

        if creds and creds.expired and creds.refresh_token:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    creds.refresh(Request())
                    with open(resolved_path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    is_transient = any(
                        term in err_str
                        for term in ("getaddrinfo", "nameresolution", "connection", "timeout", "transport", "failed to resolve", "11001")
                    )
                    if is_transient:
                        if attempt < max_retries:
                            time.sleep(1.5 * attempt)
                            continue
                        logger.warning("Network connection or DNS temporarily offline while refreshing token. Poller will retry once online.")
                    else:
                        logger.error("OAuth token refresh failed: %s", e)
                    return None

        return creds.token


def fetch_recent_messages(space_name: str, page_size: int = 25) -> List[dict]:
    token = get_access_token()
    if not token:
        return []
    url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"pageSize": page_size, "orderBy": "createTime desc"}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            return res.json().get("messages", [])
    except Exception:
        pass
    return []


def process_space_sync(space_name: str, is_initial: bool = False):
    with process_lock:
        msgs = fetch_recent_messages(space_name)
        msgs.sort(key=lambda x: x.get("createTime", ""))
        for m in msgs:
            mid = m.get("name")
            if not mid:
                continue

            text = m.get("text") or ""
            update_time = m.get("lastUpdateTime") or m.get("createTime") or ""
            text_hash = hash_content(text)
            sender = m.get("sender", {}).get("displayName", "User")

            if mid not in processed_messages:
                # 1. Brand new message
                processed_messages[mid] = {"update_time": update_time, "text_hash": text_hash}
                if not is_initial:
                    logger.info("  |-> [NEW MSG] From: %s | Text: %r", sender, text[:60])
                    try:
                        agent.handle_incoming_message(m, recent_space_history=msgs, is_edit=False)
                    except Exception:
                        logger.exception("Error in agent handler.")
            else:
                # 2. Existing message: Check if updated/edited
                cached = processed_messages[mid]
                is_time_updated = bool(m.get("lastUpdateTime") and m.get("lastUpdateTime") != cached.get("update_time"))
                is_text_changed = (text_hash != cached.get("text_hash"))

                if is_text_changed or is_time_updated:
                    processed_messages[mid] = {"update_time": update_time, "text_hash": text_hash}
                    if not is_initial:
                        logger.info("  |-> [EDITED MSG] From: %s | Text: %r", sender, text[:60])
                        try:
                            agent.handle_incoming_message(m, recent_space_history=msgs, is_edit=True)
                        except Exception:
                            logger.exception("Error in agent handler on edited message.")


def background_poller(space_name: str, interval: float = 2.0):
    logger.info("Live space sync loop active (syncing every %.1fs)...", interval)
    offline_notified = False
    while not stop_event.is_set():
        try:
            token = get_access_token()
            if not token:
                if not offline_notified:
                    logger.warning("Network connection or OAuth token temporarily unavailable. Pausing sync for 10s...")
                    offline_notified = True
                stop_event.wait(10.0)
                continue

            if offline_notified:
                logger.info("Network connectivity restored! Resuming live sync.")
                offline_notified = False

            process_space_sync(space_name)
        except Exception as e:
            logger.debug("Exception in space sync cycle: %s", e)

        stop_event.wait(interval)


def main():
    parser = argparse.ArgumentParser(description="Webhook Assistant Listener")
    parser.add_argument("--space", default=config.SPACE_NAME, help="Target space ID")
    parser.add_argument("--interval", type=float, default=config.POLL_INTERVAL, help="Sync interval (seconds)")
    args = parser.parse_args()

    if not args.space:
        logger.error("No GC_SPACE_NAME configured. Exiting.")
        sys.exit(1)

    logger.info("Starting Webhook Assistant Listener for %s...", args.space)
    process_space_sync(args.space, is_initial=True)
    logger.info("Initial sync complete. Tracking %d messages.", len(processed_messages))

    poller = threading.Thread(target=background_poller, args=(args.space, args.interval), daemon=True)
    poller.start()

    logger.info("Assistant is monitoring messages... (Press Ctrl+C to stop)")
    signal.signal(signal.SIGINT, lambda s, f: stop_event.set())
    signal.signal(signal.SIGTERM, lambda s, f: stop_event.set())

    while not stop_event.is_set():
        stop_event.wait(1.0)

    logger.info("Listener stopped.")


if __name__ == "__main__":
    main()
