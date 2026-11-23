"""Event payloads (docs/contracts.md, topics `order-created` and `order-ready`)."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Animal = Literal["dog", "penguin", "capybara"]


class OrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    animal: Animal
    qty: int = Field(ge=1, le=5)


class OrderCreated(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["order_created"]
    # order_id becomes part of object paths, so only a safe character set is accepted.
    order_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    customer_id: str = Field(min_length=1)
    wa_id: str = Field(pattern=r"^\d{6,15}$")
    items: list[OrderItem] = Field(min_length=1)
    created_at: AwareDatetime

    def animals_per_image(self) -> list[Animal]:
        """One entry per image to generate, in item order."""
        return [item.animal for item in self.items for _ in range(item.qty)]


def order_ready_event(order: OrderCreated, images: list[str], ready_at: datetime) -> dict:
    return {
        "type": "order_ready",
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "wa_id": order.wa_id,
        "images": images,
        "ready_at": to_iso(ready_at),
    }


def to_iso(moment: datetime) -> str:
    """UTC ISO 8601 with a `Z` suffix, as in the contract examples."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
