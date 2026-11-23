"""EventPublisher backed by `shared.pubsub.publish_json`."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from mcp_shop.domain.orders import Order


def order_created_payload(order: Order) -> dict[str, Any]:
    """The `order-created` message as defined in docs/contracts.md."""
    return {
        "type": "order_created",
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "wa_id": order.wa_id,
        "items": [{"animal": line.animal.value, "qty": line.qty} for line in order.lines],
        "created_at": order.created_at.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


@dataclass(frozen=True)
class PubSubEventPublisher:
    publish_json: Callable[[str, dict[str, Any]], str]
    order_created_topic: str

    async def order_created(self, order: Order) -> None:
        await asyncio.to_thread(
            self.publish_json, self.order_created_topic, order_created_payload(order)
        )


def shared_event_publisher(order_created_topic: str) -> PubSubEventPublisher:
    from shared.pubsub import publish_json

    return PubSubEventPublisher(publish_json, order_created_topic)
