"""
GitHub "server" entry for the registry.

Unlike agent_scope_server.py and asana_server.py, this file does NOT run
an MCP server — GitHub already runs and maintains one for us at
https://api.githubcopilot.com/mcp/ (see your diagram: "Github Remote MCP
Server", connected over HTTP, not spawned as a local stdio subprocess).

This file's only job is to describe *how to connect* to that remote
server, so the registry (mcp_global_server.py) can open a session to it
the same way it opens sessions to our local servers — just over HTTP
instead of stdio. This is also why there's no github_client.py: there's
no REST API to wrap, we're just being an MCP client to someone else's
MCP server.
"""

import os
from contextlib import asynccontextmanager

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"


class GitHubAuthError(Exception):
    """Raised when GITHUB_PERSONAL_ACCESS_TOKEN is missing."""


def _require_token() -> str:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise GitHubAuthError(
            "GITHUB_PERSONAL_ACCESS_TOKEN is not set. Create one at "
            "https://github.com/settings/tokens (repo scope is enough for "
            "reading PR diffs) and put it in your .env file."
        )
    return token


@asynccontextmanager
async def github_mcp_session():
    """
    Open a live MCP session against GitHub's remote server.

    Usage (from the registry or host):
        async with github_mcp_session() as session:
            tools = await session.list_tools()
            result = await session.call_tool("get_pull_request", {...})

    This mirrors how ClientSession is used for our stdio-based servers —
    the registry doesn't need to know GitHub's server is remote and
    someone else's code; it just gets a session either way.
    """
    token = _require_token()
    http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})

    async with streamable_http_client(GITHUB_MCP_URL, http_client=http_client) as (
        read,
        write,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session