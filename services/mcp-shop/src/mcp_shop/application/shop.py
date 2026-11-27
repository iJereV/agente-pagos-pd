"""The application facade the MCP server drives.

Every tool call first drains the caller's order outbox, then runs its use case.
"""

from dataclasses import dataclass
from typing import Any

from mcp_shop.application.create_order import CreateOrder
from mcp_shop.application.get_balance import GetBalance
from mcp_shop.application.get_order_status import GetOrderStatus
from mcp_shop.application.order_events import OrderEvents
from mcp_shop.application.outcomes import (
    Balance,
    Credited,
    NotEnoughBalance,
    OrderCreated,
    OrderStatusView,
    Rejected,
)
from mcp_shop.application.verify_receipt import VerifyReceipt
from mcp_shop.domain.identity import Caller
from mcp_shop.ports.tokens import TokenVerifier


@dataclass(frozen=True)
class Shop:
    tokens: TokenVerifier
    order_events: OrderEvents
    balance: GetBalance
    ordering: CreateOrder
    receipts: VerifyReceipt
    order_status: GetOrderStatus

    async def get_balance(self, caller: Caller) -> Balance | Rejected:
        await self.order_events.flush(caller.customer_id)
        return await self.balance(caller)

    async def create_order(
        self, caller: Caller, raw_items: Any
    ) -> OrderCreated | NotEnoughBalance | Rejected:
        await self.order_events.flush(caller.customer_id)
        return await self.ordering(caller, raw_items)

    async def verify_receipt(self, caller: Caller) -> Credited | Rejected:
        await self.order_events.flush(caller.customer_id)
        return await self.receipts(caller)

    async def get_order_status(self, caller: Caller, order_id: str) -> OrderStatusView | Rejected:
        await self.order_events.flush(caller.customer_id)
        return await self.order_status(caller, order_id)
