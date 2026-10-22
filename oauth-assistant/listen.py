"""
Multi-space real-time space listener with silent token refresh.
"""

import argparse
import logging
import os
import signal
import sys
import threading
import hashlib
from typing import Dict, List

import requests

import agent
import auth
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
logger = logging.getLogger("oauth-listener")

process_lock = threading.Lock()
stop_event = threading.Event()
# Tracks message ID -> {"update_time": str, "text_hash": str}
processed_messages: Dict[str, dict] = {}


def hash_content(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def fetch_recent_messages(space_name: str, page_size: int = 25) -> List[dict]:
    creds = auth.get_valid_credentials()
    if not creds:
        return []

    url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    headers = {"Authorization": f"Bearer {creds.token}"}
    params = {"pageSize": page_size, "orderBy": "createTime desc"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            return res.json().get("messages", [])
        else:
            logger.error("Chat API error (%d): %s", res.status_code, res.text)
    except requests.exceptions.RequestException as e:
        logger.debug("Transient network error during message fetch: %s", e)
    except Exception:
        logger.exception("Unexpected error fetching messages.")
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
                        agent.handle_incoming_message(m, target_space=space_name, recent_space_history=msgs, is_edit=False)
                    except Exception:
                        logger.exception("Error in agent handler.")
            else:
                # 2. Existing message: Check if text or update timestamp changed (Edited Message)
                cached = processed_messages[mid]
                is_time_updated = bool(m.get("lastUpdateTime") and m.get("lastUpdateTime") != cached.get("update_time"))
                is_text_changed = (text_hash != cached.get("text_hash"))

                if is_text_changed or is_time_updated:
                    processed_messages[mid] = {"update_time": update_time, "text_hash": text_hash}
                    if not is_initial:
                        logger.info("  |-> [EDITED MSG] From: %s | Text: %r", sender, text[:60])
                        try:
                            agent.handle_incoming_message(m, target_space=space_name, recent_space_history=msgs, is_edit=True)
                        except Exception:
                            logger.exception("Error in agent handler on edited message.")


def background_poller(space_name: str, interval: float = 2.0):
    logger.info("Live space sync loop active for %s (every %.1fs)...", space_name, interval)
    offline_notified = False
    while not stop_event.is_set():
        try:
            creds = auth.get_valid_credentials()
            if not creds:
                if not offline_notified:
                    logger.warning("Network connection or OAuth credentials temporarily unavailable. Pausing sync for 10s...")
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
    parser = argparse.ArgumentParser(description="User-Delegated OAuth Space Listener")
    parser.add_argument("--space", default=config.SPACE_NAME, help="Target space ID (e.g. spaces/XXXXXXXXXXX)")
    parser.add_argument("--interval", type=float, default=config.POLL_INTERVAL, help="Sync interval (seconds)")
    parser.add_argument("--token", default=config.TOKEN_PATH, help="Path to token.json")
    args = parser.parse_args()

    if args.token:
        config.TOKEN_PATH = args.token

    if not args.space:
        logger.error("No target space configured. Specify via --space or GC_SPACE_NAME in .env.")
        sys.exit(1)

    # Verify credentials
    creds = auth.get_valid_credentials()
    if not creds:
        logger.error("No valid credentials found at %s. Please run 'python auth.py' first!", config.TOKEN_PATH)
        sys.exit(1)

    logger.info("Starting User-Delegated Space Listener...")
    logger.info("Target Space: %s", args.space)
    logger.info("Token File:   %s", config.TOKEN_PATH)

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
