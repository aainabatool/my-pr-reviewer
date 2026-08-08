"""
Webhook — the FastAPI Server piece from your diagram (step 2: receives
the "PR opened" event from GitHub).

Flow on a valid webhook:
  1. Verify GitHub's HMAC signature (reject anything not actually from
     GitHub — this endpoint is publicly reachable).
  2. Respond to GitHub immediately (it expects a fast response and will
     retry/timeout otherwise) while the real work happens in a
     background task.
  3. Background task: fetch the PR diff, fetch the review prompt
     (agent_scope.pr_review), ask Gemini to review it, post the result
     to Slack.

Note: steps 5/6/8 in your diagram ("LLM selects tools and arguments",
"invoke tools") describe a full agentic tool-calling loop — the LLM
deciding on its own which MCP tools to call. This file implements a
simpler fixed pipeline instead (diff -> prompt -> LLM -> Slack) as a
working first version. Wiring Gemini's function-calling against the
MCP tool schemas to let it choose tools dynamically is a natural next
step once this baseline is solid.
"""

import hashlib
import hmac
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from pr_reviewer_mcp_host.host.llm_gateway import LLMGateway
from pr_reviewer_mcp_host.host.mcp_client import MCPClient

router = APIRouter()


def verify_github_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """
    GitHub sends X-Hub-Signature-256: "sha256=<hex digest>", computed as
    HMAC-SHA256 of the raw request body using your configured webhook
    secret. hmac.compare_digest is used instead of == specifically to
    avoid timing-attack side channels on the comparison.
    """
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_WEBHOOK_SECRET is not configured on the server.",
        )
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _fetch_pr_diff(diff_url: str) -> str:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(diff_url, headers=headers)
    response.raise_for_status()
    return response.text


async def process_pr_review(payload: dict) -> None:
    """The background task: the actual review pipeline."""
    pr = payload["pull_request"]
    diff = await _fetch_pr_diff(pr["diff_url"])
    # Diffs can be large; keep the prompt a reasonable size for now.
    diff_excerpt = diff[:8000]

    async with MCPClient() as client:
        review_prompt = await client.get_prompt(
            "agent_scope.pr_review", {"focus_areas": "correctness and readability"}
        )

        llm = LLMGateway()
        full_prompt = (
            f"{review_prompt}\n\n"
            f"PR title: {pr['title']}\n"
            f"PR description: {pr.get('body') or '(no description)'}\n\n"
            f"Diff:\n{diff_excerpt}"
        )
        review_text = await llm.generate(full_prompt)

        channel = os.environ.get("SLACK_REVIEW_CHANNEL", "#all-mcp")
        message = f"*PR Review: {pr['title']}* ({pr['html_url']})\n\n{review_text}"
        await client.invoke_tool("slack.post_slack_message", {"channel": channel, "text": message})


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_github_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()

    if event == "pull_request" and payload.get("action") in ("opened", "synchronize"):
        background_tasks.add_task(process_pr_review, payload)
        return {"status": "accepted"}

    # Not an event we care about (e.g. a PR comment, a label change) —
    # acknowledge it so GitHub doesn't retry, but do nothing.
    return {"status": "ignored"}