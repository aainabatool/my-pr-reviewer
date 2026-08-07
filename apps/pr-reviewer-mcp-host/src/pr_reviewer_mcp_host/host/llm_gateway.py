"""
LLM Gateway.

The piece your diagram labels "LLM Gateway" inside the MCP Host — talks
to Gemini (steps 4, 5, 8: query with the PR review prompt, select tools
and arguments, query again with tool responses). Nothing MCP-specific
lives here; this file only knows how to ask Gemini a question and get
text back. The MCP orchestration (deciding which tools to call, in
what order) lives in mcp_client.py, one layer up.
"""

import os

from google import genai

DEFAULT_MODEL = "gemini-3.5-flash"


class LLMGatewayError(Exception):
    """Raised when GEMINI_API_KEY is missing or the API call fails."""


class LLMGateway:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise LLMGatewayError(
                "GEMINI_API_KEY is not set. Get one at "
                "https://aistudio.google.com/apikey and put it in your .env file."
            )
        self._client = genai.Client(api_key=resolved_key)
        self._model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    async def generate(self, prompt: str) -> str:
        """
        Send a single prompt to Gemini and return its text response.

        Deliberately minimal for now — no tool-calling, no chat history.
        mcp_client.py will build on top of this once we get there (step
        5's "select tools and arguments" needs Gemini's function-calling
        support, which we'll add when that file wires the two together).
        """
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        if not response.text:
            raise LLMGatewayError("Gemini returned an empty response.")
        return response.text