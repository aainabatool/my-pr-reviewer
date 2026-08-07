"""
Slack MCP Server.

Exposes one MCP tool: post a review result to a channel (diagram step 9,
"Send final review to Slack"). Requires SLACK_BOT_TOKEN in the
environment — obtained via the one-time OAuth install flow in
slack_oauth_install.py, not typed in by hand like Asana's PAT.
"""

import os
import sys

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from pr_reviewer_mcp_servers.clients.slack_client import SlackAuthError, SlackClient

load_dotenv()

mcp = MCPServer(name="slack-server")


@mcp.tool(
    name="post_slack_message",
    description=(
        "Post a message to a Slack channel — used to deliver the final "
        "PR review result to the team channel."
    ),
)
async def post_slack_message(channel: str, text: str) -> dict:
    """
    Args:
        channel: Channel ID or name, e.g. "#pr-reviews" or "C0123456789".
        text: The message to post (typically the rendered PR review).
    """
    client = SlackClient(bot_token=os.environ.get("SLACK_BOT_TOKEN"))
    try:
        return await client.post_message(channel, text)
    except SlackAuthError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    if not os.environ.get("SLACK_BOT_TOKEN"):
        print(
            "WARNING: SLACK_BOT_TOKEN not set. Run slack_oauth_install.py "
            "once to obtain one via OAuth, then set it in .env.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")