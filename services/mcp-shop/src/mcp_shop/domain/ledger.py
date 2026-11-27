"""A customer's prepaid ledger: a balance that orders debit and transfers credit.

The balance never goes negative. Every change is also a `Movement` with a deterministic
id, so storing it with a create-only write makes each change happen at most once.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from mcp_shop.domain.catalog import OrderLine, order_total_cents
from mcp_shop.domain.orders import Order


class MovementKind(StrEnum):
    WELCOME_CREDIT = "welcome_credit"
    ORDER = "order"
    PAYMENT = "payment"


@dataclass(frozen=True)
class Movement:
    movement_id: str
    customer_id: str
    kind: MovementKind
    amount_cents: int
    """Signed: credits are positive, order debits negative."""
    balance_after_cents: int
    created_at: datetime
    reference: str | None = None
    """The order id or payment key the movement comes from, if any."""


def welcome_movement_id(customer_id: str) -> str:
    """One welcome credit per customer: its id is derived from the customer alone."""
    return f"welcome:{customer_id}"


@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    balance_cents: int
    """Balance right after the order was debited."""


class InsufficientBalance(Exception):
    def __init__(self, balance_cents: int, total_cents: int) -> None:
        super().__init__(f"balance {balance_cents} cents does not cover {total_cents} cents")
        self.balance_cents = balance_cents
        self.total_cents = total_cents

    @property
    def payment_needed_cents(self) -> int:
        return self.total_cents - self.balance_cents


@dataclass
class Ledger:
    customer_id: str
    balance_cents: int
    welcome_credit_granted: bool
    movements: list[Movement] = field(default_factory=list)
    """Movements made since the ledger was loaded, still to be stored."""

    def grant_welcome_credit(self, amount_cents: int, at: datetime) -> None:
        """Credit the one-time welcome credit unless it was already granted."""
        if self.welcome_credit_granted or amount_cents <= 0:
            return
        self.welcome_credit_granted = True
        self._move(
            welcome_movement_id(self.customer_id), MovementKind.WELCOME_CREDIT, amount_cents, at
        )

    def place_order(
        self,
        *,
        order_id: str,
        wa_id: str,
        lines: tuple[OrderLine, ...],
        created_at: datetime,
    ) -> PlacedOrder:
        """Debit the order total, which must be covered by the balance."""
        total = order_total_cents(lines)
        if total > self.balance_cents:
            raise InsufficientBalance(self.balance_cents, total)
        self._move(f"order:{order_id}", MovementKind.ORDER, -total, created_at, order_id)
        order = Order(
            order_id=order_id,
            customer_id=self.customer_id,
            wa_id=wa_id,
            lines=lines,
            total_cents=total,
            paid_cents=total,
            created_at=created_at,
        )
        return PlacedOrder(order, self.balance_cents)

    def credit_payment(self, payment_key: str, amount_cents: int, at: datetime) -> None:
        """Add a verified transfer to the balance."""
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        self._move(f"payment:{payment_key}", MovementKind.PAYMENT, amount_cents, at, payment_key)

    def _move(
        self,
        movement_id: str,
        kind: MovementKind,
        amount_cents: int,
        at: datetime,
        reference: str | None = None,
    ) -> None:
        self.balance_cents += amount_cents
        self.movements.append(
            Movement(
                movement_id=movement_id,
                customer_id=self.customer_id,
                kind=kind,
                amount_cents=amount_cents,
                balance_after_cents=self.balance_cents,
                created_at=at,
                reference=reference,
            )
        )
