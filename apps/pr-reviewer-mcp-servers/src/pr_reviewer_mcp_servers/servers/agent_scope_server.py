"""
Agent Scope MCP Server.

Serves the PR review prompt as an MCP *prompt template*. The host (step 3
in the architecture) fetches this prompt and can pass arguments to steer
the review — e.g. focus on security, or go easy on style nits — without
any Python code changing on the host side.

This server has no external API calls and no auth. It's the simplest
piece in the system, which is why we're building it first.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="agent-scope-server")


@mcp.prompt(
    name="pr_review",
    description="Generates the instructions used to review a pull request.",
)
def pr_review_prompt(
    focus_areas: str = "correctness, readability, and obvious bugs",
    strictness: str = "balanced — flag real issues, don't nitpick style",
) -> str:
    """
    Build the PR review prompt handed to the LLM.

    Args:
        focus_areas: What the reviewer should pay the most attention to.
            Examples: "security vulnerabilities", "performance",
            "test coverage".
        strictness: How harsh the review should be.
            Examples: "strict — block on any issue",
            "lenient — only flag blockers".
    """
    return f"""You are reviewing a pull request as a senior engineer.

Focus areas: {focus_areas}
Review strictness: {strictness}

For the PR diff and any linked issue context you're given, produce:
1. A one-paragraph summary of what the PR does.
2. A list of specific, line-referenced issues (if any), ordered by severity.
3. A clear verdict: APPROVE, REQUEST_CHANGES, or COMMENT.

Be concrete. Reference actual lines and reasons, not generic advice.
If the diff looks fine, say so briefly and approve — don't invent problems
to seem thorough.

Formatting: this will be posted directly to Slack, so use Slack's
mrkdwn syntax, not standard Markdown:
- Bold with single asterisks: *bold*, never **bold**.
- Do NOT use "#" headers. Instead, put a section label in bold on its
  own line, e.g. "*Summary*" followed by a blank line then the text.
- Use "-" or "•" for bullet points, never numbered "1." lists for the
  issues section.
- No horizontal rules ("---"), no HTML, no code fences unless quoting
  actual code.
"""


if __name__ == "__main__":
    # stdio transport: the host spawns this as a subprocess and talks to
    # it over stdin/stdout. Matches how MCP hosts usually connect to
    # locally-run servers (vs. GitHub's *remote* MCP server, which the
    # host connects to over HTTP instead).
    mcp.run(transport="stdio")