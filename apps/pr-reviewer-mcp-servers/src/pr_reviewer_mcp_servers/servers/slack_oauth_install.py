"""
One-time Slack OAuth install flow.

Run this once, in a browser, to obtain a bot token for your workspace.
This is NOT the MCP server — it's a standalone helper. Slack's OAuth
flow needs a browser redirect back to a web server, which doesn't fit
inside a stdio MCP server (no HTTP listener there). So this script:

  1. Opens Slack's authorize URL in your browser.
  2. Runs a tiny local HTTP server just long enough to catch the
     redirect (with the auth code) at http://localhost:3000/slack/callback.
  3. Exchanges that code for a bot token.
  4. Prints the token so you can paste it into .env as SLACK_BOT_TOKEN.

Requires SLACK_CLIENT_ID and SLACK_CLIENT_SECRET in your environment —
get these by creating a Slack app at https://api.slack.com/apps,
adding the "chat:write" bot scope, and setting this script's redirect
URL (http://localhost:3000/slack/callback) under OAuth & Permissions.

Usage:
    uv run python src/pr_reviewer_mcp_servers/servers/slack_oauth_install.py
"""

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

REDIRECT_URI = "http://localhost:3000/slack/callback"
SCOPES = "chat:write"

_received_code: dict[str, str | None] = {"code": None}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        _received_code["code"] = code

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = (
            "Authorized — you can close this tab and return to the terminal."
            if code
            else "No authorization code received. Check the terminal for errors."
        )
        self.wfile.write(f"<html><body><h2>{message}</h2></body></html>".encode())

    def log_message(self, *args) -> None:
        pass  # silence default request logging


def main() -> None:
    client_id = os.environ.get("SLACK_CLIENT_ID")
    client_secret = os.environ.get("SLACK_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "SLACK_CLIENT_ID and SLACK_CLIENT_SECRET must be set in .env "
            "(from your Slack app's 'Basic Information' page) before "
            "running this installer."
        )

    authorize_url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}&scope={SCOPES}&redirect_uri={REDIRECT_URI}"
    )
    print(f"Opening browser for Slack authorization:\n{authorize_url}\n")
    webbrowser.open(authorize_url)

    server = HTTPServer(("localhost", 3000), _CallbackHandler)
    print("Waiting for Slack redirect on http://localhost:3000/slack/callback ...")
    server.handle_request()  # blocks for exactly one request, then returns

    code = _received_code["code"]
    if not code:
        raise SystemExit("No authorization code received. Aborting.")

    response = httpx.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    data = response.json()

    if not data.get("ok"):
        raise SystemExit(f"Slack rejected the token exchange: {data.get('error')}")

    bot_token = data["access_token"]
    print("\nSuccess. Add this to your .env file:\n")
    print(f"SLACK_BOT_TOKEN={bot_token}")


if __name__ == "__main__":
    main()