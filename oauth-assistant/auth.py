"""
Authentication module for User-Delegated OAuth Assistant.
Provides:
1. Thread-safe silent background token refresh.
2. Browserless / Headless authentication for remote servers or desktop terminals.
"""

import argparse
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
import time
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("oauth-auth")
_token_lock = threading.Lock()


def get_valid_credentials(token_path: str = None) -> Optional[Credentials]:
    """
    Retrieves valid user credentials. Silently auto-refreshes expired tokens.
    Includes transient network resilience for computer sleep/wake and Wi-Fi reconnections.
    """
    path = token_path or config.TOKEN_PATH
    if not os.path.exists(path):
        return None

    with _token_lock:
        try:
            creds = Credentials.from_authorized_user_file(path, config.SCOPES)
        except Exception as e:
            logger.error("Failed to parse token file %s: %s", path, e)
            return None

        if creds and creds.expired and creds.refresh_token:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    creds.refresh(Request())
                    with open(path, "w", encoding="utf-8") as f:
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

        return creds


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this tab and return to the terminal.</p>")
        else:
            self.send_response(400)
            self.end_headers()


def authenticate_flow(
    credentials_file: str = None,
    output_token_file: str = None,
    headless: bool = True,
    port: int = 8080,
) -> bool:
    creds_file = credentials_file or config.CREDENTIALS_PATH
    token_file = output_token_file or config.TOKEN_PATH

    if not os.path.exists(creds_file):
        print(f"\n[ERROR] Credentials file not found: {creds_file}")
        print("Please place your OAuth client JSON file in the project folder.")
        return False

    print("=" * 70)
    print("User-Delegated OAuth Authenticator")
    print(f"Credentials source: {creds_file}")
    print(f"Output token:       {token_file}")
    print("=" * 70)

    flow = InstalledAppFlow.from_client_secrets_file(creds_file, config.SCOPES)
    flow.redirect_uri = f"http://localhost:{port}/"

    if not headless:
        print("\nOpening local browser for authentication...")
        creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"\nSUCCESS! Token saved to: {token_file}")
        return True

    # Headless / Browserless flow
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    print("\n" + "=" * 70)
    print(">> OPEN THIS URL IN ANY BROWSER TO LOG IN:")
    print("=" * 70)
    print(auth_url)
    print("=" * 70)

    httpd = HTTPServer(("localhost", port), OAuthCallbackHandler)
    httpd.auth_code = None
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    print("\n[Option 1] If opening on this machine: Click 'Allow' in your browser.")
    print("[Option 2] If authorizing on another device: Paste the redirect URL or code below:")

    class ConsoleListener(threading.Thread):
        def __init__(self):
            super().__init__(daemon=True)
            self.user_input = None

        def run(self):
            try:
                val = input("Paste redirect URL or Code: ").strip()
                if val:
                    self.user_input = val
            except (EOFError, KeyboardInterrupt):
                pass

    console_thread = ConsoleListener()
    console_thread.start()

    auth_code = None
    while True:
        if httpd.auth_code:
            auth_code = httpd.auth_code
            print("\n[INFO] Authorization code received via local redirect!")
            break
        if console_thread.user_input:
            raw = console_thread.user_input
            if "code=" in raw:
                parsed = parse_qs(urlparse(raw).query)
                auth_code = parsed.get("code", [raw])[0]
            else:
                auth_code = raw
            print("\n[INFO] Authorization code received via manual paste!")
            break
        console_thread.join(timeout=0.5)

    httpd.shutdown()

    try:
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"\nSUCCESS! Token saved to: {token_file}")
        print("This token includes a permanent refresh token for silent background renewal.")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to exchange token: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="OAuth 2.0 Authenticator")
    parser.add_argument("--creds", default=config.CREDENTIALS_PATH, help="Path to credentials JSON")
    parser.add_argument("--output", default=config.TOKEN_PATH, help="Path to save token JSON")
    parser.add_argument("--browser", action="store_true", help="Launch local browser automatically")
    parser.add_argument("--port", type=int, default=8080, help="Local redirect port")
    args = parser.parse_args()

    authenticate_flow(
        credentials_file=args.creds,
        output_token_file=args.output,
        headless=not args.browser,
        port=args.port,
    )


if __name__ == "__main__":
    main()
