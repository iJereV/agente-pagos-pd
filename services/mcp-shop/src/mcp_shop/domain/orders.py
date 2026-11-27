"""Orders. New orders are paid from the balance when placed.

`unpaid` and `partially_paid` only appear on orders stored under the earlier credit model.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from mcp_shop.domain.catalog import OrderLine


class OrderStatus(StrEnum):
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"


@dataclass
class Order:
    order_id: str
    customer_id: str
    wa_id: str
    lines: tuple[OrderLine, ...]
    total_cents: int
    paid_cents: int
    created_at: datetime

    @property
    def status(self) -> OrderStatus:
        if self.paid_cents >= self.total_cents:
            return OrderStatus.PAID
        if self.paid_cents > 0:
            return OrderStatus.PARTIALLY_PAID
        return OrderStatus.UNPAID
