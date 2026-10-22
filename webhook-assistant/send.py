"""
Standalone CLI tool to post messages to Google Chat via Webhook.
"""

import argparse
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
WEBHOOK_URL = os.getenv("CHAT_WEBHOOK_URL")


def send_message(text: str, webhook_url: str = None) -> bool:
    url = webhook_url or WEBHOOK_URL
    if not url:
        print("\n[ERROR] CHAT_WEBHOOK_URL is not set in .env!")
        return False

    payload = {"text": text}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code in (200, 201):
            print("\n[SUCCESS] Message posted via Webhook!")
            return True
        else:
            print(f"\n[ERROR] Webhook status {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"\n[ERROR] Request failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send message via Webhook")
    parser.add_argument("message", nargs="*", help="Message text to send")
    parser.add_argument("--file", "-f", help="Send contents of file")
    args = parser.parse_args()

    text = ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    elif args.message:
        text = " ".join(args.message).strip()
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        print("Enter message to send (Press Enter on blank line to finish):")
        lines = []
        while True:
            try:
                line = input()
                if not line and lines:
                    break
                lines.append(line)
            except (EOFError, KeyboardInterrupt):
                sys.exit(0)
        text = "\n".join(lines).strip()

    if not text:
        print("Error: Empty message.")
        sys.exit(1)

    success = send_message(text)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
