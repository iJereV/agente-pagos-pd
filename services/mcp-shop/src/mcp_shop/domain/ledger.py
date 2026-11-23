"""A customer's ledger: credit balance plus unpaid orders. Enforces the credit rule."""

from dataclasses import dataclass, field
from datetime import datetime

from mcp_shop.domain.allocation import AllocationResult, allocate
from mcp_shop.domain.catalog import OrderLine, order_total_cents
from mcp_shop.domain.orders import Order


class CreditLimitExceeded(Exception):
    def __init__(self, available_credit_cents: int) -> None:
        super().__init__(f"credit limit exceeded, available {available_credit_cents} cents")
        self.available_credit_cents = available_credit_cents


@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    credit_used_cents: int


@dataclass
class Ledger:
    customer_id: str
    credit_balance_cents: int
    unpaid_orders: list[Order] = field(default_factory=list)

    @property
    def debt_cents(self) -> int:
        return sum(order.outstanding_cents for order in self.unpaid_orders)

    def available_credit_cents(self, credit_limit_cents: int) -> int:
        return max(0, credit_limit_cents - self.debt_cents + self.credit_balance_cents)

    def place_order(
        self,
        *,
        order_id: str,
        wa_id: str,
        lines: tuple[OrderLine, ...],
        created_at: datetime,
        credit_limit_cents: int,
    ) -> PlacedOrder:
        """Accept when `debt - credit_balance + total <= limit`; credit balance pays first."""
        total = order_total_cents(lines)
        if self.debt_cents - self.credit_balance_cents + total > credit_limit_cents:
            raise CreditLimitExceeded(self.available_credit_cents(credit_limit_cents))
        credit_used = min(self.credit_balance_cents, total)
        order = Order(
            order_id=order_id,
            customer_id=self.customer_id,
            wa_id=wa_id,
            lines=lines,
            total_cents=total,
            paid_cents=credit_used,
            created_at=created_at,
        )
        self.credit_balance_cents -= credit_used
        if order.outstanding_cents > 0:
            self.unpaid_orders.append(order)
        return PlacedOrder(order, credit_used)

    def apply_payment(self, amount_cents: int) -> AllocationResult:
        """Pay the oldest orders first and keep the remainder as credit balance."""
        result = allocate(amount_cents, self.unpaid_orders)
        self.credit_balance_cents += result.remainder_cents
        return result
