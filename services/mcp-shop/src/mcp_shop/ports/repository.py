"""Persistence port. Writes that move money run as one transaction each."""

from collections.abc import Callable
from typing import Protocol

from mcp_shop.domain.ledger import Ledger, PlacedOrder
from mcp_shop.domain.orders import Order
from mcp_shop.domain.payments import ManualReview, RecordedPayment


class ShopRepository(Protocol):
    async def load_ledger(self, customer_id: str) -> Ledger:
        """Credit balance and unpaid orders (oldest first). Missing account means zero."""
        ...

    async def get_order(self, order_id: str) -> Order | None: ...

    async def place_order(
        self, customer_id: str, place: Callable[[Ledger], PlacedOrder]
    ) -> PlacedOrder:
        """In one transaction: load the ledger, run `place`, store the order and account.

        The order is stored with `event_published=false` (outbox). `place` may run more
        than once if the transaction retries, so it must be pure.
        """
        ...

    async def orders_pending_event(self, customer_id: str) -> list[Order]:
        """The customer's orders whose `order_created` event was not published yet."""
        ...

    async def mark_event_published(self, order_id: str) -> None: ...

    async def record_payment(
        self, customer_id: str, payment_key: str, apply: Callable[[Ledger], RecordedPayment]
    ) -> RecordedPayment:
        """In one transaction: claim `payments/{payment_key}`, run `apply`, store the result.

        Raises `PaymentAlreadyRecorded` when the payment document already exists.
        """
        ...

    async def save_manual_review(self, review: ManualReview) -> None: ...
