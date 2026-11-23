"""Driving adapter: MCP tools over streamable HTTP at `/mcp`, plus `GET /health`.

Identity comes only from the signed `X-Turn-Token` header. No tool argument carries it.
"""

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_shop.application.shop import Shop
from mcp_shop.domain.identity import Caller
from mcp_shop.ports.tokens import InvalidTurnToken

TURN_TOKEN_HEADER = "x-turn-token"

ITEMS_DESCRIPTION = (
    'Order lines, e.g. [{"animal": "dog", "qty": 2}]. '
    "animal is one of dog, penguin, capybara; qty is 1 to 5."
)


def build_server(shop: Shop) -> MCPServer:
    server = MCPServer(
        name="mcp-shop",
        instructions="Shop tools. The customer is taken from the turn token, never from arguments.",
    )

    async def caller(ctx: Context) -> Caller:
        headers = {k.lower(): v for k, v in (ctx.headers or {}).items()}
        token = headers.get(TURN_TOKEN_HEADER)
        if not token:
            raise ToolError("missing turn token")
        try:
            return await shop.tokens.verify(token)
        except InvalidTurnToken as error:
            raise ToolError("invalid turn token") from error

    @server.tool()
    async def get_balance(ctx: Context) -> dict[str, Any]:
        """Debt, credit balance, available credit and unpaid orders. Needs a fresh sign-in."""
        return _json(await shop.get_balance(await caller(ctx)))

    @server.tool()
    async def create_order(
        items: Annotated[list[dict[str, Any]], Field(description=ITEMS_DESCRIPTION)],
        ctx: Context,
    ) -> dict[str, Any]:
        """Place an order on credit, priced by the shop. Needs a fresh sign-in."""
        return _json(await shop.create_order(await caller(ctx), items))

    @server.tool()
    async def verify_receipt(ctx: Context) -> dict[str, Any]:
        """Verify the customer's last transfer receipt and credit the payment."""
        return _json(await shop.verify_receipt(await caller(ctx)))

    @server.tool()
    async def get_order_status(order_id: str, ctx: Context) -> dict[str, Any]:
        """Payment status of one of the customer's orders."""
        return _json(await shop.get_order_status(await caller(ctx), order_id))

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return server


def build_app(shop: Shop) -> Starlette:
    # Stateless JSON responses suit Cloud Run: any instance can answer any call.
    # Host checks are off because Cloud Run IAM is the network boundary.
    return build_server(shop).streamable_http_app(
        stateless_http=True, json_response=True, host="0.0.0.0"
    )


def _json(outcome: BaseModel) -> dict[str, Any]:
    return outcome.model_dump(mode="json")
