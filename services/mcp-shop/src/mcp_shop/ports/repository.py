"""Persistence port. Writes that move money run as one transaction each.

Each money-moving method loads the ledger inside its transaction, runs a pure function on
it and then stores the ledger's new movements with create-only writes plus the account
balance. A movement that already exists fails the commit, so nothing is applied twice.
"""

from collections.abc import Callable
from typing import Protocol

from mcp_shop.domain.ledger import Ledger, PlacedOrder
from mcp_shop.domain.orders import Order
from mcp_shop.domain.payments import ManualReview, RecordedPayment


class ShopRepository(Protocol):
    async def update_ledger(self, customer_id: str, update: Callable[[Ledger], None]) -> Ledger:
        """In one transaction: load the ledger, run `update`, store movements and account.

        A missing account means a zero balance without the welcome credit. `update` may
        run more than once if the transaction retries, so it must be pure.
        """
        ...

    async def get_order(self, order_id: str) -> Order | None: ...

    async def place_order(
        self, customer_id: str, place: Callable[[Ledger], PlacedOrder]
    ) -> PlacedOrder:
        """In one transaction: load the ledger, run `place`, store the order and ledger.

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
