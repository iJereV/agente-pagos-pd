"""``wa-inbound`` consumer: customer messages and system events."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from main_worker.application import Clock
from main_worker.application.conversation import Conversation
from main_worker.application.deliveries import OrderDeliveries
from main_worker.domain.errors import PermanentError
from main_worker.domain.models import CustomerMessage, Identity, SystemEvent
from main_worker.domain.rendering import customer_turn_input, receipt_path, system_event_input
from main_worker.ports import ChannelStore, MediaStore, WhatsApp

logger = logging.getLogger(__name__)


class InboundHandler:
    def __init__(
        self,
        *,
        store: ChannelStore,
        whatsapp: WhatsApp,
        media: MediaStore,
        conversation: Conversation,
        deliveries: OrderDeliveries,
        clock: Clock,
    ) -> None:
        self._store = store
        self._whatsapp = whatsapp
        self._media = media
        self._conversation = conversation
        self._deliveries = deliveries
        self._clock = clock

    async def handle(self, payload: dict[str, Any]) -> None:
        match payload.get("type"):
            case "customer_message":
                message = CustomerMessage.from_payload(payload)
                await self._once(message.wamid, lambda: self._customer_message(message))
            case "system_event":
                event = SystemEvent.from_payload(payload)
                await self._once(event.event_id, lambda: self._system_event(event))
            case other:
                raise PermanentError(f"unknown wa-inbound type: {other!r}")

    async def _once(self, message_id: str, work: Callable[[], Awaitable[None]]) -> None:
        """Run ``work`` at most once per id; release the claim unless it failed permanently."""
        if not await self._store.claim_message(message_id, self._clock()):
            logger.info("duplicate message dropped", extra={"message_id": message_id})
            return
        try:
            await work()
        except PermanentError:
            raise
        except BaseException:  # Includes cancellation: the retry must not be deduped.
            await self._store.release_message(message_id)
            raise

    async def _customer_message(self, message: CustomerMessage) -> None:
        identity = await self._conversation.identify(message.wa_id)
        receipt_ref = await self._store_media(message, identity) if message.has_media else None
        turn = await self._conversation.run_turn(
            identity,
            customer_turn_input(message),
            customer_inbound=True,
            new_receipt_ref=receipt_ref,
        )
        if turn.reply:
            await self._whatsapp.send_text(message.wa_id, turn.reply)
        await self._deliveries.deliver_pending(message.wa_id)

    async def _system_event(self, event: SystemEvent) -> None:
        identity = await self._conversation.identify(event.wa_id)
        # The customer id never reaches the model: identity lives in session state.
        fields = {k: v for k, v in event.data.items() if k != "customer_id"}
        turn = await self._conversation.run_turn(
            identity, system_event_input(event.event, **fields), customer_inbound=False
        )
        if not turn.reply:
            return
        if not turn.window_open:
            logger.warning("system event reply dropped: outside the 24 h window")
            return
        await self._whatsapp.send_text(event.wa_id, turn.reply)

    async def _store_media(self, message: CustomerMessage, identity: Identity) -> str:
        media = await self._whatsapp.download_media(message.media_id)
        mime_type = message.mime_type or media.mime_type
        path = receipt_path(identity.customer_id or identity.wa_id, message.wamid, mime_type)
        await self._media.put(path, media.data, mime_type)
        logger.info("stored inbound media", extra={"wamid": message.wamid, "path": path})
        return path
