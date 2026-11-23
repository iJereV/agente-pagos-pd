"""Orders and their payment status."""

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
    def outstanding_cents(self) -> int:
        return self.total_cents - self.paid_cents

    @property
    def status(self) -> OrderStatus:
        if self.paid_cents >= self.total_cents:
            return OrderStatus.PAID
        if self.paid_cents > 0:
            return OrderStatus.PARTIALLY_PAID
        return OrderStatus.UNPAID

    def pay(self, amount_cents: int) -> None:
        if not 0 < amount_cents <= self.outstanding_cents:
            raise ValueError("payment must be positive and at most the outstanding amount")
        self.paid_cents += amount_cents
