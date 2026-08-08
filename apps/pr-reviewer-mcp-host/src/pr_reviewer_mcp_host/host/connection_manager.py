"""
Connections Manager.

The piece your diagram labels "Connections Manager" inside the MCP Host.
Owns the lifecycle of the ONE connection the host makes: to
registry_server.py in the servers app. Nothing here knows about
"tools" or "prompts" as concepts — that's mcp_client.py's job, one
layer up. This file only knows how to start that process and hand back
a live session.

Cross-app wrinkle worth understanding: the host and servers are
separate uv projects with separate virtual environments.
registry_server.py needs the pr_reviewer_mcp_servers package to run,
and that package only exists in the SERVERS app's venv — not the
host's. So we can't spawn it with sys.executable (that's the host's
own interpreter, which doesn't have that package). We have to point at
the servers app's venv interpreter explicitly.
"""

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Assumes the standard monorepo layout: apps/pr-reviewer-mcp-host and
# apps/pr-reviewer-mcp-servers are siblings. Overridable via env vars
# for anyone whose layout differs.
_DEFAULT_SERVERS_APP_DIR = Path(__file__).parents[4] / "pr-reviewer-mcp-servers"


class ConnectionManagerError(Exception):
    """Raised when the servers app's venv/script can't be located."""


def _servers_app_dir() -> Path:
    override = os.environ.get("MCP_SERVERS_APP_DIR")
    return Path(override) if override else _DEFAULT_SERVERS_APP_DIR


def _servers_venv_python(servers_dir: Path) -> Path:
    # venv layout differs by OS: Scripts\python.exe on Windows,
    # bin/python on Linux/macOS.
    windows_python = servers_dir / ".venv" / "Scripts" / "python.exe"
    unix_python = servers_dir / ".venv" / "bin" / "python"
    if windows_python.exists():
        return windows_python
    if unix_python.exists():
        return unix_python
    raise ConnectionManagerError(
        f"Could not find the servers app's venv Python under {servers_dir}. "
        f"Make sure you've run 'uv sync' in pr-reviewer-mcp-servers, or set "
        f"MCP_SERVERS_APP_DIR in .env if your folder layout differs."
    )


class ConnectionManager:
    """
    Spawns registry_server.py (in the servers app's venv) and holds the
    live MCP session to it.

    Usage:
        async with ConnectionManager() as conn:
            session = conn.session
            tools = await session.list_tools()
    """

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "ConnectionManager":
        servers_dir = _servers_app_dir()
        python_path = _servers_venv_python(servers_dir)
        script_path = (
            servers_dir
            / "src"
            / "pr_reviewer_mcp_servers"
            / "registry"
            / "registry_server.py"
        )
        if not script_path.exists():
            raise ConnectionManagerError(f"registry_server.py not found at {script_path}")

        params = StdioServerParameters(
            command=str(python_path),
            args=[str(script_path)],
        )

        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.__aexit__(*exc_info)