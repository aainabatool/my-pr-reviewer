"""
MCP Client.

The piece your diagram labels "MCP Client" inside the MCP Host — the
thing that actually invokes tools (step 6) and sends the final review
to Slack (step 9). ConnectionManager owns the raw connection; this
file owns what you DO with it, so the rest of the host (webhook.py,
main.py) never has to think about ClientSession, stdio, or any MCP
plumbing at all — just "invoke this tool with these arguments."
"""

from pr_reviewer_mcp_host.host.connection_manager import ConnectionManager


class MCPClient:
    """
    Usage:
        async with MCPClient() as client:
            tools = await client.list_tools()
            result = await client.invoke_tool("asana.get_asana_task", {"task_gid": "123"})
            prompt = await client.get_prompt("agent_scope.pr_review", {"focus_areas": "security"})
    """

    def __init__(self) -> None:
        self._conn: ConnectionManager | None = None

    async def __aenter__(self) -> "MCPClient":
        self._conn = ConnectionManager()
        await self._conn.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._conn.__aexit__(*exc_info)

    async def list_tools(self) -> list[str]:
        result = await self._conn.session.list_tools()
        return [t.name for t in result.tools]

    async def invoke_tool(self, qualified_name: str, arguments: dict) -> str:
        """
        Call a tool by its qualified name (e.g. "asana.get_asana_task",
        "slack.post_slack_message", "github.get_pull_request") and
        return its text result.
        """
        result = await self._conn.session.call_tool(qualified_name, arguments)
        if not result.content:
            return ""
        return result.content[0].text

    async def get_prompt(self, qualified_name: str, arguments: dict) -> str:
        """
        Fetch a rendered prompt by its qualified name (e.g.
        "agent_scope.pr_review") and return the rendered text.
        """
        result = await self._conn.session.get_prompt(qualified_name, arguments)
        return result.messages[0].content.text