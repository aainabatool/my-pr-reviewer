"""
MCP Global Server (Registry).

This is the piece your diagram labels "MCP Global Server (Registry)" —
sitting under agent-scope, asana, github, and slack, aggregating all
four into one thing the host talks to. The host never opens a
connection to Asana's server directly; it asks the registry, and the
registry routes to whichever backend server actually owns that tool.

Two kinds of backends are wired in:
  - stdio servers (agent_scope, asana, slack): we spawn them as Python
    subprocesses and talk over stdin/stdout.
  - remote HTTP servers (github): already running on GitHub's
    infrastructure, we just open a session to it.

Tool/prompt names are qualified as "server_name.item_name" (e.g.
"asana.get_asana_task") so the registry knows which backend to route a
call to, and so two servers can never silently collide on a name.
"""

import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pr_reviewer_mcp_servers.servers.github_server import github_mcp_session

# mcp_global_server.py lives in registry/, but the server scripts we
# spawn live in the sibling servers/ folder — not the same directory.
SERVERS_DIR = Path(__file__).parent.parent / "servers"


@dataclass
class StdioServerSpec:
    name: str
    script: str  # filename relative to servers/, e.g. "asana_server.py"


# Local servers we spawn ourselves. Add slack_server.py here once it
# exists — nothing else in this file needs to change.
STDIO_SERVERS = [
    StdioServerSpec(name="agent_scope", script="agent_scope_server.py"),
    StdioServerSpec(name="asana", script="asana_server.py"),
]

# Remote servers someone else runs. Each entry is an async context
# manager factory that yields a live ClientSession, same shape as
# github_mcp_session.
REMOTE_SERVERS: dict[str, Callable] = {
    "github": github_mcp_session,
}


class MCPRegistry:
    """
    Aggregates every backend MCP server behind one interface.

    Usage:
        async with MCPRegistry() as registry:
            tools = await registry.list_all_tools()
            result = await registry.call_tool("asana.get_asana_task", {"task_gid": "123"})
            prompt = await registry.get_prompt("agent_scope.pr_review", {"focus_areas": "security"})
    """

    def __init__(self, include: set[str] | None = None) -> None:
        # `include` lets the host connect to a subset (e.g. skip github
        # if no token is configured yet) instead of all-or-nothing.
        self._include = include
        self._stack: AsyncExitStack | None = None
        self.sessions: dict[str, ClientSession] = {}

    async def __aenter__(self) -> "MCPRegistry":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for spec in STDIO_SERVERS:
            if self._include and spec.name not in self._include:
                continue
            params = StdioServerParameters(
                # sys.executable, not the string "python" — guarantees the
                # spawned server uses the exact same interpreter (and
                # therefore the same installed packages) as the registry
                # itself, regardless of what "python" resolves to on PATH.
                command=sys.executable,
                args=[str(SERVERS_DIR / spec.script)],
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[spec.name] = session

        for name, session_factory in REMOTE_SERVERS.items():
            if self._include and name not in self._include:
                continue
            session = await self._stack.enter_async_context(session_factory())
            self.sessions[name] = session

        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.__aexit__(*exc_info)

    def _split(self, qualified_name: str) -> tuple[str, str]:
        server_name, _, item_name = qualified_name.partition(".")
        if not item_name:
            raise ValueError(
                f"Expected 'server_name.item_name' (e.g. 'asana.get_asana_task'), "
                f"got: {qualified_name!r}"
            )
        if server_name not in self.sessions:
            raise ValueError(
                f"No connected server named {server_name!r}. "
                f"Connected: {list(self.sessions)}"
            )
        return server_name, item_name

    async def list_all_tools(self) -> dict[str, list[str]]:
        result = {}
        for name, session in self.sessions.items():
            tools = await session.list_tools()
            result[name] = [t.name for t in tools.tools]
        return result

    async def list_all_prompts(self) -> dict[str, list[str]]:
        result = {}
        for name, session in self.sessions.items():
            prompts = await session.list_prompts()
            result[name] = [p.name for p in prompts.prompts]
        return result

    async def call_tool(self, qualified_name: str, arguments: dict):
        server_name, tool_name = self._split(qualified_name)
        return await self.sessions[server_name].call_tool(tool_name, arguments)

    async def get_prompt(self, qualified_name: str, arguments: dict):
        server_name, prompt_name = self._split(qualified_name)
        return await self.sessions[server_name].get_prompt(prompt_name, arguments)