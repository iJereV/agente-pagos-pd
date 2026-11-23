"""Port for domain events leaving the service."""

from typing import Protocol

from mcp_shop.domain.orders import Order


class EventPublisher(Protocol):
    async def order_created(self, order: Order) -> None: ...
