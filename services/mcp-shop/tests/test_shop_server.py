"""End to end over streamable HTTP: the turn token header is the only identity."""

from collections.abc import Iterator
from typing import Any

import pytest
from mcp_shop.server import build_app
from shop_fakes import World, caller
from starlette.testclient import TestClient

HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    world.tokens.callers["fresh-token"] = caller()
    world.tokens.callers["unlinked-token"] = caller(customer_id=None)
    with TestClient(build_app(world.shop)) as test_client:
        yield test_client


def call_tool(
    client: TestClient, name: str, arguments: dict[str, Any], token: str | None
) -> dict[str, Any]:
    headers = dict(HEADERS)
    if token:
        headers["x-turn-token"] = token
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    assert client.post("/mcp", json=initialize, headers=headers).status_code == 200
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    response = client.post("/mcp", json=request, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_tool_reads_identity_from_the_turn_token(client: TestClient, world: World):
    result = call_tool(
        client, "create_order", {"items": [{"animal": "dog", "qty": 1}]}, "fresh-token"
    )
    assert result["structuredContent"]["status"] == "created"
    assert world.publisher.orders[0].customer_id == "cust-synthetic-1"


def test_unlinked_token_gets_a_closed_outcome(client: TestClient):
    result = call_tool(client, "get_balance", {}, "unlinked-token")
    assert result["structuredContent"] == {"status": "not_linked"}


@pytest.mark.parametrize("token", [None, "forged-token"])
def test_missing_or_invalid_token_is_a_tool_error(client: TestClient, token: str | None):
    result = call_tool(client, "get_balance", {}, token)
    assert result["isError"] is True
