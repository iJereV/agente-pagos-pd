"""Per-request headers for the mcp-shop connection.

ADK calls the header provider with a ReadonlyContext before listing and before
calling MCP tools, so every request carries headers built from the current session.
"""

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import google.auth.transport.requests
from google.adk.agents.readonly_context import ReadonlyContext
from google.oauth2 import id_token

TURN_TOKEN_STATE_KEY = "turn_token"
TURN_TOKEN_HEADER = "X-Turn-Token"

IdTokenFetcher = Callable[[str], str]
HeaderProvider = Callable[[ReadonlyContext], Awaitable[dict[str, str]]]


def fetch_google_id_token(audience: str) -> str:
    """Fetches a Google-signed ID token for the runtime service account (metadata server)."""
    return id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)


def audience_for(mcp_url: str) -> str:
    """Cloud Run IAM accepts the service base URL as the ID token audience."""
    parts = urlsplit(mcp_url)
    return f"{parts.scheme}://{parts.netloc}"


def make_header_provider(
    audience: str, fetch_id_token: IdTokenFetcher = fetch_google_id_token
) -> HeaderProvider:
    """Builds the header provider: Cloud Run IAM bearer token plus the session turn token."""

    async def provide(context: ReadonlyContext) -> dict[str, str]:
        # The fetch is a blocking HTTP call; keep it off the event loop.
        token = await asyncio.to_thread(fetch_id_token, audience)
        headers = {"Authorization": f"Bearer {token}"}
        turn_token = context.state.get(TURN_TOKEN_STATE_KEY)
        if turn_token:
            headers[TURN_TOKEN_HEADER] = str(turn_token)
        return headers

    return provide
