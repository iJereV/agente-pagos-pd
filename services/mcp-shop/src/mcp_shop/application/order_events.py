"""Outbox for `order_created`: orders are committed first, announced after.

An order is stored with `event_published=false`. After the commit the event is published
with a short retry; only then is the flag set. Orders left unpublished are announced again
on the customer's next tool call. Consumers are idempotent per order, so a repeat is harmless.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mcp_shop.domain.orders import Order
from mcp_shop.ports.events import EventPublisher
from mcp_shop.ports.repository import ShopRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderEvents:
    repository: ShopRepository
    events: EventPublisher
    attempts: int = 3
    first_backoff_seconds: float = 0.2
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def publish(self, order: Order) -> bool:
        """Publish with exponential backoff and mark the order. Never raises."""
        for attempt in range(self.attempts):
            if attempt:
                await self.sleep(self.first_backoff_seconds * 2 ** (attempt - 1))
            try:
                await self.events.order_created(order)
            except Exception:
                logger.warning(
                    "order_created publish failed",
                    extra={"order_id": order.order_id, "attempt": attempt + 1},
                    exc_info=True,
                )
                continue
            try:
                await self.repository.mark_event_published(order.order_id)
            except Exception:
                # Published but not marked: it will be published again, which is safe.
                logger.exception("marking order event failed", extra={"order_id": order.order_id})
            return True
        logger.error("order_created left in outbox", extra={"order_id": order.order_id})
        return False

    async def flush(self, customer_id: str | None) -> None:
        """Re-publish the customer's pending order events. Never raises."""
        if not customer_id:
            return
        try:
            pending = await self.repository.orders_pending_event(customer_id)
        except Exception:
            logger.exception("reading the order outbox failed", extra={"customer_id": customer_id})
            return
        for order in pending:
            if not await self.publish(order):
                return  # The publisher is down; keep the rest for the next call.
