"""ShopRepository on the named Firestore database `shop`.

Layout (docs/contracts.md): `accounts/{customer_id}`, `movements/{movement_id}`,
`orders/{order_id}`, `payments/{e2e_id}`, `manual_reviews/{id}`.
"""

from collections.abc import Callable
from typing import Any

from google.cloud import firestore
from google.cloud.firestore import (
    AsyncClient,
    AsyncTransaction,
    FieldFilter,
    async_transactional,
)

from mcp_shop.domain.catalog import Animal, OrderLine
from mcp_shop.domain.ledger import Ledger, Movement, PlacedOrder, welcome_movement_id
from mcp_shop.domain.orders import Order
from mcp_shop.domain.payments import ManualReview, PaymentAlreadyRecorded, RecordedPayment

ACCOUNTS = "accounts"
MOVEMENTS = "movements"
ORDERS = "orders"
PAYMENTS = "payments"
MANUAL_REVIEWS = "manual_reviews"
EVENT_PUBLISHED = "event_published"
"""Outbox flag on `orders/{order_id}`: false until `order_created` is published."""
LEGACY_CREDIT_BALANCE = "credit_balance_cents"
"""Account field of the earlier credit model, read as the balance until first rewritten."""


class FirestoreShopRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._db = client

    @classmethod
    def for_database(cls, project: str | None, database: str) -> "FirestoreShopRepository":
        return cls(firestore.AsyncClient(project=project, database=database))

    async def update_ledger(self, customer_id: str, update: Callable[[Ledger], None]) -> Ledger:
        @async_transactional
        async def run(transaction: AsyncTransaction) -> Ledger:
            ledger = await self._read_ledger(customer_id, transaction)
            update(ledger)
            self._write_ledger(transaction, ledger)
            return ledger

        return await run(self._db.transaction())

    async def get_order(self, order_id: str) -> Order | None:
        snapshot = await self._db.collection(ORDERS).document(order_id).get()
        return _order_from_doc(snapshot.id, snapshot.to_dict()) if snapshot.exists else None

    async def place_order(
        self, customer_id: str, place: Callable[[Ledger], PlacedOrder]
    ) -> PlacedOrder:
        @async_transactional
        async def run(transaction: AsyncTransaction) -> PlacedOrder:
            ledger = await self._read_ledger(customer_id, transaction)
            placed = place(ledger)
            order = placed.order
            transaction.create(
                self._db.collection(ORDERS).document(order.order_id),
                {**_order_doc(order), EVENT_PUBLISHED: False},
            )
            self._write_ledger(transaction, ledger)
            return placed

        return await run(self._db.transaction())

    async def orders_pending_event(self, customer_id: str) -> list[Order]:
        pending = (
            self._db.collection(ORDERS)
            .where(filter=FieldFilter("customer_id", "==", customer_id))
            .where(filter=FieldFilter(EVENT_PUBLISHED, "==", False))
        )
        snapshots = await pending.get()
        return sorted(
            (_order_from_doc(s.id, s.to_dict()) for s in snapshots), key=lambda o: o.created_at
        )

    async def mark_event_published(self, order_id: str) -> None:
        await self._db.collection(ORDERS).document(order_id).update({EVENT_PUBLISHED: True})

    async def record_payment(
        self, customer_id: str, payment_key: str, apply: Callable[[Ledger], RecordedPayment]
    ) -> RecordedPayment:
        payment_ref = self._db.collection(PAYMENTS).document(payment_key)

        @async_transactional
        async def run(transaction: AsyncTransaction) -> RecordedPayment:
            if (await payment_ref.get(transaction=transaction)).exists:
                raise PaymentAlreadyRecorded(payment_key)
            ledger = await self._read_ledger(customer_id, transaction)
            payment = apply(ledger)
            # `create` fails on commit if a concurrent receipt claimed the same transfer.
            transaction.create(payment_ref, _payment_doc(payment))
            self._write_ledger(transaction, ledger)
            return payment

        return await run(self._db.transaction())

    async def save_manual_review(self, review: ManualReview) -> None:
        await (
            self._db.collection(MANUAL_REVIEWS)
            .document(review.review_id)
            .set(
                {
                    "customer_id": review.customer_id,
                    "receipt_ref": review.receipt_ref,
                    "reason": review.reason.value,
                    "extracted": review.extracted,
                    "candidates": [c.summary() for c in review.candidates],
                    "created_at": review.created_at,
                }
            )
        )

    async def _read_ledger(self, customer_id: str, transaction: AsyncTransaction) -> Ledger:
        # Reading the welcome movement inside the transaction makes a concurrent grant
        # conflict and retry, and its create-only write fails if it already exists.
        account = (
            await self._db.collection(ACCOUNTS).document(customer_id).get(transaction=transaction)
        )
        welcome = (
            await self._db.collection(MOVEMENTS)
            .document(welcome_movement_id(customer_id))
            .get(transaction=transaction)
        )
        return Ledger(
            customer_id=customer_id,
            balance_cents=_account_balance(account.to_dict() if account.exists else None),
            welcome_credit_granted=welcome.exists,
        )

    def _write_ledger(self, transaction: AsyncTransaction, ledger: Ledger) -> None:
        if not ledger.movements:
            return
        for movement in ledger.movements:
            transaction.create(
                self._db.collection(MOVEMENTS).document(movement.movement_id),
                _movement_doc(movement),
            )
        transaction.set(
            self._db.collection(ACCOUNTS).document(ledger.customer_id),
            {"balance_cents": ledger.balance_cents, LEGACY_CREDIT_BALANCE: firestore.DELETE_FIELD},
            merge=True,
        )


def _account_balance(data: dict[str, Any] | None) -> int:
    data = data or {}
    return int(data.get("balance_cents", data.get(LEGACY_CREDIT_BALANCE, 0)))


def _movement_doc(movement: Movement) -> dict[str, Any]:
    return {
        "customer_id": movement.customer_id,
        "kind": movement.kind.value,
        "amount_cents": movement.amount_cents,
        "balance_after_cents": movement.balance_after_cents,
        "reference": movement.reference,
        "created_at": movement.created_at,
    }


def _order_doc(order: Order) -> dict[str, Any]:
    return {
        "customer_id": order.customer_id,
        "wa_id": order.wa_id,
        "items": [{"animal": line.animal.value, "qty": line.qty} for line in order.lines],
        "total_cents": order.total_cents,
        "paid_cents": order.paid_cents,
        "status": order.status.value,
        "created_at": order.created_at,
    }


def _order_from_doc(order_id: str, data: dict[str, Any] | None) -> Order:
    data = data or {}
    return Order(
        order_id=order_id,
        customer_id=data["customer_id"],
        wa_id=data.get("wa_id", ""),
        lines=tuple(OrderLine(Animal(i["animal"]), int(i["qty"])) for i in data["items"]),
        total_cents=int(data["total_cents"]),
        paid_cents=int(data["paid_cents"]),
        created_at=data["created_at"],
    )


def _payment_doc(payment: RecordedPayment) -> dict[str, Any]:
    transfer = payment.transfer
    return {
        "provider": transfer.provider,
        "provider_payment_id": transfer.provider_payment_id,
        "amount_cents": transfer.amount_cents,
        "received_at": transfer.received_at,
        "payer_cuit": transfer.payer_cuit,
        "customer_id": payment.customer_id,
        "match_method": payment.match_method.value,
        "receipt_ref": payment.receipt_ref,
        "created_at": payment.created_at,
    }
