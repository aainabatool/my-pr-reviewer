"""
Asana MCP Server.

Exposes one MCP *tool* (not a prompt or resource — tools are for actions
the LLM decides to invoke, like "fetch this task"). This is the pattern
slack_server.py will follow too: wrap a REST API client in an MCP tool
with a clear docstring, since the LLM reads that docstring to decide
when to call it.

Requires ASANA_ACCESS_TOKEN in the environment (see .env.example).
"""

import os
import sys

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from pr_reviewer_mcp_servers.clients.asana_client import AsanaAuthError, AsanaClient

load_dotenv()

mcp = MCPServer(name="asana-server")


@mcp.tool(
    name="get_asana_task",
    description=(
        "Fetch details of an Asana task by its GID, so a PR review can "
        "reference the linked task's requirements. Returns task name, "
        "description notes, completion status, due date, and assignee."
    ),
)
async def get_asana_task(task_gid: str) -> dict:
    """
    Args:
        task_gid: The numeric Asana task ID, e.g. "1234567890123456".
            Usually pulled from a task URL like
            https://app.asana.com/0/{project}/1234567890123456
    """
    client = AsanaClient(access_token=os.environ.get("ASANA_ACCESS_TOKEN"))
    try:
        return await client.get_task(task_gid)
    except AsanaAuthError as e:
        # Surface auth problems as a clear error the LLM can relay to the
        # user, rather than a raw 401 traceback.
        return {"error": str(e)}


if __name__ == "__main__":
    if not os.environ.get("ASANA_ACCESS_TOKEN"):
        print(
            "WARNING: ASANA_ACCESS_TOKEN not set. The server will start, "
            "but get_asana_task calls will fail until you set it in .env.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")