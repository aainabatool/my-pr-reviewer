"""
Thin wrapper around the Asana REST API.

Deliberately dumb: no MCP concepts here, no prompt logic, just "give me
task data as a dict." This separation is why swapping Asana for Jira
later only means rewriting this one file plus asana_server.py -> jira_server.py,
never touching the host or the other servers.
"""

import os

import httpx

ASANA_BASE_URL = "https://app.asana.com/api/1.0"


class AsanaAuthError(Exception):
    """Raised when the Asana access token is missing or rejected."""


class AsanaClient:
    def __init__(self, access_token: str | None = None) -> None:
        self._token = access_token or os.environ.get("ASANA_ACCESS_TOKEN")
        if not self._token:
            raise AsanaAuthError(
                "ASANA_ACCESS_TOKEN is not set. Create a Personal Access "
                "Token at https://app.asana.com/0/developer-console and "
                "put it in your .env file."
            )

    async def get_task(self, task_gid: str) -> dict:
        """
        Fetch a single task by its Asana GID.

        Returns the fields the PR review prompt actually needs, not the
        full Asana payload (which includes a lot of noise: custom fields,
        followers, workspace metadata, etc).
        """
        url = f"{ASANA_BASE_URL}/tasks/{task_gid}"
        params = {"opt_fields": "name,notes,completed,due_on,assignee.name"}
        headers = {"Authorization": f"Bearer {self._token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)

        if response.status_code == 401:
            raise AsanaAuthError("Asana rejected the access token (401).")
        response.raise_for_status()

        data = response.json()["data"]
        return {
            "gid": task_gid,
            "name": data.get("name"),
            "notes": data.get("notes"),
            "completed": data.get("completed"),
            "due_on": data.get("due_on"),
            "assignee": (data.get("assignee") or {}).get("name"),
        }