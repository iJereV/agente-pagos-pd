"""Use case: pay an order from the prepaid balance and announce it for image generation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mcp_shop.application.access import freshly_signed_in_customer
from mcp_shop.application.ids import new_order_id, utc_now
from mcp_shop.application.order_events import OrderEvents
from mcp_shop.application.outcomes import NotEnoughBalance, OrderCreated, Rejected
from mcp_shop.domain.catalog import MAX_QTY, MIN_QTY, Animal, OrderLine
from mcp_shop.domain.identity import Caller
from mcp_shop.domain.ledger import InsufficientBalance, Ledger, PlacedOrder
from mcp_shop.ports.repository import ShopRepository

MAX_LINES = 10


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    animal: Animal
    qty: Annotated[int, Field(ge=MIN_QTY, le=MAX_QTY, strict=True)]


_ITEMS = TypeAdapter(Annotated[list[ItemInput], Field(min_length=1, max_length=MAX_LINES)])


def parse_items(raw_items: Any) -> tuple[OrderLine, ...] | None:
    """Validate untrusted tool input into order lines, or `None` when invalid."""
    try:
        items = _ITEMS.validate_python(raw_items)
    except ValidationError:
        return None
    return tuple(OrderLine(item.animal, item.qty) for item in items)


@dataclass(frozen=True)
class CreateOrder:
    repository: ShopRepository
    order_events: OrderEvents
    welcome_credit_cents: int
    new_order_id: Callable[[], str] = new_order_id
    clock: Callable[[], datetime] = utc_now

    async def __call__(
        self, caller: Caller, raw_items: Any
    ) -> OrderCreated | NotEnoughBalance | Rejected:
        customer_id = freshly_signed_in_customer(caller)
        if isinstance(customer_id, Rejected):
            return customer_id
        lines = parse_items(raw_items)
        if lines is None:
            return Rejected(status="invalid_items")

        order_id, created_at = self.new_order_id(), self.clock()

        def place(ledger: Ledger) -> PlacedOrder:
            ledger.grant_welcome_credit(self.welcome_credit_cents, created_at)
            return ledger.place_order(
                order_id=order_id, wa_id=caller.wa_id, lines=lines, created_at=created_at
            )

        try:
            placed = await self.repository.place_order(customer_id, place)
        except InsufficientBalance as short:
            return NotEnoughBalance(
                balance_cents=short.balance_cents,
                total_cents=short.total_cents,
                payment_needed_cents=short.payment_needed_cents,
            )

        # The order is committed: answer `created` even if the event stays in the outbox,
        # since failing the tool would invite a duplicate order.
        await self.order_events.publish(placed.order)

        return OrderCreated(
            order_id=placed.order.order_id,
            total_cents=placed.order.total_cents,
            balance_cents=placed.balance_cents,
        )
