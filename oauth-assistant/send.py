"""
Universal CLI tool to send messages to ANY Google Chat space via User OAuth.
"""

import argparse
import os
import sys
import requests
from dotenv import load_dotenv

import auth
import config

load_dotenv(override=True)


def list_accessible_spaces():
    creds = auth.get_valid_credentials()
    if not creds:
        print("[ERROR] No valid credentials found. Please run 'python auth.py' first!")
        sys.exit(1)

    url = "https://chat.googleapis.com/v1/spaces?pageSize=100"
    headers = {"Authorization": f"Bearer {creds.token}"}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"[ERROR] Failed to list spaces ({res.status_code}): {res.text}")
        return

    spaces = res.json().get("spaces", [])
    print("=" * 70)
    print(f"Accessible Spaces ({len(spaces)} total):")
    print("=" * 70)
    for i, s in enumerate(spaces, 1):
        name = s.get("name")
        title = s.get("displayName") or "(Direct 1:1 or Group Chat)"
        stype = s.get("spaceType") or s.get("type", "SPACE")
        print(f"{i:2d}. [{stype}] {title}")
        print(f"    ID: {name}")


def list_recent_users(space_name: str = None):
    creds = auth.get_valid_credentials()
    if not creds:
        print("[ERROR] No valid credentials found. Please run 'python auth.py' first!")
        sys.exit(1)

    target_space = (space_name or config.SPACE_NAME or "").strip()
    if target_space.startswith("space/") and not target_space.startswith("spaces/"):
        target_space = "spaces/" + target_space[6:]

    if not target_space:
        # Auto-discover first space
        url = "https://chat.googleapis.com/v1/spaces?pageSize=5"
        headers = {"Authorization": f"Bearer {creds.token}"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200 and res.json().get("spaces"):
            target_space = res.json()["spaces"][0]["name"]
        else:
            print("[ERROR] No space specified. Pass --space spaces/YOUR_SPACE_ID")
            return

    url = f"https://chat.googleapis.com/v1/{target_space}/messages?pageSize=30&orderBy=createTime desc"
    headers = {"Authorization": f"Bearer {creds.token}"}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"[ERROR] Failed to fetch space messages ({res.status_code}): {res.text}")
        return

    messages = res.json().get("messages", [])
    seen_users = {}
    for m in messages:
        sender = m.get("sender", {})
        uid = sender.get("name")
        dname = sender.get("displayName") or "Unknown"
        email = sender.get("email") or ""
        if uid and uid not in seen_users:
            seen_users[uid] = (dname, email)

    print("=" * 70)
    print(f"Discovered Users & IDs in '{target_space}':")
    print("=" * 70)
    if not seen_users:
        print("No recent messages found in this space to extract user IDs.")
        print("Tip: Post a quick message in the space and run this command again.")
    else:
        for uid, (dname, email) in seen_users.items():
            email_info = f" ({email})" if email else ""
            print(f"• Name:    {dname}{email_info}")
            print(f"  User ID: {uid}")
            print(f"  In .env: BOT_USER_ID={uid}")
            print("-" * 70)


def send_user_message(space_name: str, text: str) -> bool:
    creds = auth.get_valid_credentials()
    if not creds:
        print("[ERROR] No valid credentials found. Please run 'python auth.py' first!")
        return False

    url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code in (200, 201):
            print(f"\n[SUCCESS] Message posted via User OAuth to {space_name}!")
            return True
        else:
            print(f"\n[ERROR] Google Chat API Error ({res.status_code}):")
            print(res.text)
            return False
    except Exception as e:
        print(f"\n[ERROR] Request failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send messages via User-Delegated OAuth")
    parser.add_argument("message", nargs="*", help="Message text to send")
    parser.add_argument("--space", "-s", default=config.SPACE_NAME, help="Target space ID (e.g. spaces/XXXXXXXXXXX)")
    parser.add_argument("--file", "-f", help="Send contents of a text file")
    parser.add_argument("--list-spaces", "-l", action="store_true", help="List all spaces the user has access to")
    parser.add_argument("--list-users", "--whoami", "-u", action="store_true", help="List users and their IDs discovered in the space")
    parser.add_argument("--token", "-t", default=config.TOKEN_PATH, help="Path to token JSON file")
    args = parser.parse_args()

    if args.token:
        config.TOKEN_PATH = args.token

    if args.list_spaces:
        list_accessible_spaces()
        return

    if args.list_users:
        list_recent_users(args.space)
        return

    text = ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    elif args.message:
        text = " ".join(args.message).strip()
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        print("=" * 60)
        print("User OAuth Assistant - Quick Messenger")
        print(f"Target Space: {args.space}")
        print("=" * 60)
        print("Enter message (Press Enter on blank line to finish):")
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

    if not args.space:
        print("Error: Target space ID required. Set GC_SPACE_NAME in .env or pass --space.")
        sys.exit(1)

    success = send_user_message(args.space, text)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
