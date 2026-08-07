"""
Thin wrapper around the Slack Web API.

Same philosophy as asana_client.py: no MCP concepts here, just "post
this text to this channel." Swapping Slack for Discord/Teams later
means rewriting this file plus slack_server.py, nothing else.
"""

import os

import httpx

SLACK_API_BASE = "https://slack.com/api"


class SlackAuthError(Exception):
    """Raised when the Slack bot token is missing or Slack rejects it."""


class SlackClient:
    def __init__(self, bot_token: str | None = None) -> None:
        self._token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        if not self._token:
            raise SlackAuthError(
                "SLACK_BOT_TOKEN is not set. Run the one-time OAuth "
                "installer (slack_oauth_install.py) to obtain one, then "
                "put it in your .env file."
            )

    async def post_message(self, channel: str, text: str) -> dict:
        """
        Post a message to a channel.

        Args:
            channel: Channel ID (e.g. "C0123456789") or name (e.g.
                "#pr-reviews" — Slack accepts both for bot-token calls).
            text: Message body.
        """
        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {"channel": channel, "text": text}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage", headers=headers, json=payload
            )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            if error in ("invalid_auth", "not_authed", "account_inactive"):
                raise SlackAuthError(f"Slack rejected the bot token: {error}")
            raise RuntimeError(f"Slack API error: {error}")

        return {"channel": data.get("channel"), "ts": data.get("ts")}