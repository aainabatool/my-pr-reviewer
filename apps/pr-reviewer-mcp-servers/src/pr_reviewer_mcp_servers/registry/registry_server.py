"""
Registry Server — the runnable form of "MCP Global Server (Registry)".

mcp_global_server.py's MCPRegistry class is a *client*: something our
own code uses to talk to all four backend servers at once. This file
turns that into a *server*: one process the host can spawn and connect
to as a single MCP server, which internally holds the registry
connections and re-exposes every backend tool/prompt as its own.

This is the piece that makes your diagram accurate — the host's MCP
Client only ever opens ONE connection (to this file), never four.

How it works: on startup, connect to every backend server via
MCPRegistry, ask each one what tools/prompts it has, then dynamically
build a matching Python function for each one (so normal MCP schema
generation works) and register it under a qualified name like
"asana.get_asana_task". Calls get forwarded straight back through the
registry to the real backend.
"""

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts.base import Prompt

from pr_reviewer_mcp_servers.registry.mcp_global_server import MCPRegistry

mcp = MCPServer(name="pr-reviewer-registry")

# JSON Schema type -> Python type, for building wrapper function signatures.
_SCHEMA_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "dict",
    "array": "list",
}


def _build_tool_wrapper(registry: MCPRegistry, qualified_name: str, input_schema: dict):
    """
    Dynamically build an async function whose signature matches
    input_schema, so MCPServer's normal introspection produces the
    correct tool schema for the LLM — instead of a generic
    "arguments: dict" that would hide parameter names/types from Gemini.
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    params = []
    for prop_name, prop_schema in properties.items():
        py_type = _SCHEMA_TYPE_MAP.get(prop_schema.get("type"), "str")
        if prop_name in required:
            params.append(f"{prop_name}: {py_type}")
        else:
            params.append(f"{prop_name}: {py_type} = None")

    # Sort so required params come first (Python doesn't allow a
    # default-valued param before a non-default one).
    params.sort(key=lambda p: "= None" in p)
    signature = ", ".join(params)

    namespace: dict[str, Any] = {"registry": registry, "qualified_name": qualified_name}
    source = f"""
async def _wrapper({signature}):
    arguments = {{{", ".join(f"'{p.split(':')[0].strip()}': {p.split(':')[0].strip()}" for p in params)}}}
    arguments = {{k: v for k, v in arguments.items() if v is not None}}
    result = await registry.call_tool(qualified_name, arguments)
    return result.content[0].text if result.content else None
"""
    exec(source, namespace)
    return namespace["_wrapper"]


def _build_prompt_wrapper(session, prompt_name: str, arguments: list):
    """
    Same idea as _build_tool_wrapper, for prompts. PromptArgument only
    carries name/description/required (no JSON type), so every param
    is typed as str — reasonable, since prompt arguments are text.
    """
    params = []
    for arg in arguments or []:
        if arg.required:
            params.append(f"{arg.name}: str")
        else:
            params.append(f"{arg.name}: str = None")
    params.sort(key=lambda p: "= None" in p)
    signature = ", ".join(params)

    namespace: dict[str, Any] = {"session": session, "prompt_name": prompt_name}
    names = [p.split(":")[0].strip() for p in params]
    dict_literal = ", ".join(f"'{n}': {n}" for n in names)
    source = f"""
async def _prompt_wrapper({signature}) -> str:
    arguments = {{{dict_literal}}}
    arguments = {{k: v for k, v in arguments.items() if v is not None}}
    result = await session.get_prompt(prompt_name, arguments)
    return result.messages[0].content.text
"""
    exec(source, namespace)
    return namespace["_prompt_wrapper"]


async def _register_all(registry: MCPRegistry) -> None:
    for server_name, session in registry.sessions.items():
        tools = await session.list_tools()
        for tool in tools.tools:
            qualified_name = f"{server_name}.{tool.name}"
            wrapper = _build_tool_wrapper(registry, qualified_name, tool.input_schema or {})
            mcp.add_tool(wrapper, name=qualified_name, description=tool.description)

        prompts = await session.list_prompts()
        for prompt in prompts.prompts:
            qualified_name = f"{server_name}.{prompt.name}"
            wrapper = _build_prompt_wrapper(session, prompt.name, prompt.arguments)
            prompt_obj = Prompt.from_function(
                wrapper, name=qualified_name, description=prompt.description
            )
            mcp.add_prompt(prompt_obj)


async def _main() -> None:
    async with MCPRegistry() as registry:
        await _register_all(registry)
        await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(_main())