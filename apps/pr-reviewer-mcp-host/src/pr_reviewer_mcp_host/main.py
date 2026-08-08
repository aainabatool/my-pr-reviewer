"""
Main entrypoint — creates the FastAPI app (the "FastAPI Server" box in
your diagram), wires in the webhook router, and runs it with uvicorn.

Run with:
    uv run python src/pr_reviewer_mcp_host/main.py

Or, for auto-reload during development:
    uv run uvicorn pr_reviewer_mcp_host.main:app --reload --app-dir src
"""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env before anything else imports os.environ.get(...) for keys.
load_dotenv()

from pr_reviewer_mcp_host.api.webhook import router as webhook_router  # noqa: E402

app = FastAPI(title="PR Reviewer MCP Host")
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    """
    Quick liveness check — useful once this is exposed via ngrok/a real
    deployment, to confirm the server is actually reachable before
    debugging anything webhook-specific.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)