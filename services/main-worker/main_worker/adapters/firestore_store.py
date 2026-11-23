"""``ChannelStore`` on the ``channel`` Firestore database (layout in docs/contracts.md)."""

from datetime import datetime

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

from main_worker.domain.models import OrderReady, SessionPointer

AWAITING_WINDOW = "awaiting_window"
DELIVERED = "delivered"


class FirestoreChannelStore:
    def __init__(self, client: firestore.AsyncClient) -> None:
        self._db = client

    async def claim_message(self, message_id: str, now: datetime) -> bool:
        try:
            await self._processed(message_id).create({"processed_at": now})
        except AlreadyExists:
            return False
        return True

    async def release_message(self, message_id: str) -> None:
        await self._processed(message_id).delete()

    async def linked_customer(self, wa_id: str) -> str | None:
        snapshot = await self._db.collection("wa_links").document(wa_id).get()
        return snapshot.get("customer_id") if snapshot.exists else None

    async def last_sign_in(self, customer_id: str) -> datetime | None:
        snapshot = await self._db.collection("customers").document(customer_id).get()
        return (snapshot.to_dict() or {}).get("last_sign_in_at") if snapshot.exists else None

    async def session_pointer(self, wa_id: str) -> SessionPointer | None:
        snapshot = await self._db.collection("wa_sessions").document(wa_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        return SessionPointer(
            session_id=data["session_id"],
            last_activity=data["last_activity"],
            last_inbound_at=data.get("last_inbound_at"),
            last_receipt_ref=data.get("last_receipt_ref"),
        )

    async def save_session_pointer(self, wa_id: str, pointer: SessionPointer) -> None:
        await (
            self._db.collection("wa_sessions")
            .document(wa_id)
            .set(
                {
                    "session_id": pointer.session_id,
                    "last_activity": pointer.last_activity,
                    "last_inbound_at": pointer.last_inbound_at,
                    "last_receipt_ref": pointer.last_receipt_ref,
                }
            )
        )

    async def save_link_token(
        self, token_hash: str, *, wa_id: str, purpose: str, expires_at: datetime
    ) -> None:
        await (
            self._db.collection("link_tokens")
            .document(token_hash)
            .create({"wa_id": wa_id, "purpose": purpose, "expires_at": expires_at, "used_at": None})
        )

    async def delivery_status(self, order_id: str) -> str | None:
        snapshot = await self._deliveries().document(order_id).get()
        return snapshot.get("status") if snapshot.exists else None

    async def mark_delivered(self, order: OrderReady, now: datetime) -> None:
        await self._deliveries().document(order.order_id).set(_delivery(order, DELIVERED, now))

    async def mark_awaiting_window(self, order: OrderReady) -> None:
        # wa_id, customer_id and images let a later inbound message finish the delivery.
        delivery = _delivery(order, AWAITING_WINDOW, None)
        await self._deliveries().document(order.order_id).set(delivery)

    async def awaiting_deliveries(self, wa_id: str) -> list[OrderReady]:
        query = (
            self._deliveries()
            .where(filter=FieldFilter("wa_id", "==", wa_id))
            .where(filter=FieldFilter("status", "==", AWAITING_WINDOW))
        )
        return [
            OrderReady(
                order_id=snapshot.id,
                wa_id=wa_id,
                customer_id=snapshot.get("customer_id"),
                images=tuple(snapshot.get("images")),
            )
            async for snapshot in query.stream()
        ]

    def _processed(self, message_id: str):
        return self._db.collection("processed_messages").document(message_id)

    def _deliveries(self):
        return self._db.collection("deliveries")


def _delivery(order: OrderReady, status: str, delivered_at: datetime | None) -> dict:
    """``deliveries/{order_id}`` (docs/contracts.md)."""
    return {
        "status": status,
        "delivered_at": delivered_at,
        "wa_id": order.wa_id,
        "customer_id": order.customer_id,
        "images": list(order.images),
    }
