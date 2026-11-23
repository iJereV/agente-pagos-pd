"""Order delivery: agent text plus the order images, or a template outside the window."""

import logging
from pathlib import PurePosixPath

from main_worker.application import Clock
from main_worker.application.conversation import Conversation
from main_worker.domain.models import OrderReady
from main_worker.domain.policy import Policy, window_open
from main_worker.domain.rendering import content_type_for, system_event_input
from main_worker.ports import ChannelStore, MediaStore, WhatsApp

logger = logging.getLogger(__name__)


class OrderDeliveries:
    def __init__(
        self,
        *,
        store: ChannelStore,
        whatsapp: WhatsApp,
        media: MediaStore,
        conversation: Conversation,
        policy: Policy,
        clock: Clock,
    ) -> None:
        self._store = store
        self._whatsapp = whatsapp
        self._media = media
        self._conversation = conversation
        self._policy = policy
        self._clock = clock

    async def handle_order_ready(self, order: OrderReady) -> None:
        log = {"order_id": order.order_id}
        if await self._store.delivery_status(order.order_id) is not None:
            logger.info("order already handled", extra=log)
            return

        pointer = await self._store.session_pointer(order.wa_id)
        last_inbound_at = pointer.last_inbound_at if pointer else None
        if window_open(last_inbound_at, self._clock()):
            await self._deliver(order)
            return

        await self._whatsapp.send_template(
            order.wa_id, self._policy.order_ready_template, self._policy.template_language
        )
        await self._store.mark_awaiting_window(order)
        logger.info("outside the window; template sent", extra=log)

    async def deliver_pending(self, wa_id: str) -> None:
        """Deliver orders that waited for the customer to reopen the window.

        Failures are logged and left as ``awaiting_window`` for the next message, so
        they never cause the customer's own message to be processed twice.
        """
        for order in await self._store.awaiting_deliveries(wa_id):
            try:
                await self._deliver(order)
            except Exception:
                logger.exception("pending delivery failed", extra={"order_id": order.order_id})

    async def _deliver(self, order: OrderReady) -> None:
        identity = await self._conversation.identify(order.wa_id)
        turn = await self._conversation.run_turn(
            identity,
            system_event_input(
                "order_ready", order_id=order.order_id, image_count=len(order.images)
            ),
            customer_inbound=False,
        )
        if turn.reply:
            await self._whatsapp.send_text(order.wa_id, turn.reply)
        for path in order.images:
            await self._send_image(order.wa_id, path)
        await self._store.mark_delivered(order, self._clock())
        logger.info("order delivered", extra={"order_id": order.order_id})

    async def _send_image(self, wa_id: str, path: str) -> None:
        data = await self._media.get(path)
        filename = PurePosixPath(path).name
        media_id = await self._whatsapp.upload_media(data, content_type_for(path), filename)
        await self._whatsapp.send_image(wa_id, media_id)
