"""Pub/Sub push endpoints and the acknowledgement policy.

2xx acknowledges the message; 5xx makes Pub/Sub retry (and eventually dead-letter).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from shared.pubsub import decode_push

from main_worker.application.deliveries import OrderDeliveries
from main_worker.application.inbound import InboundHandler
from main_worker.domain.errors import PermanentError, TransientError
from main_worker.domain.models import OrderReady

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


def create_app(inbound: InboundHandler, deliveries: OrderDeliveries) -> FastAPI:
    app = FastAPI(title="main-worker", docs_url=None, redoc_url=None, openapi_url=None)

    async def order_ready(payload: dict[str, Any]) -> None:
        await deliveries.handle_order_ready(OrderReady.from_payload(payload))

    @app.post("/pubsub/wa-inbound")
    async def wa_inbound(request: Request) -> Response:
        return await _consume(request, inbound.handle)

    @app.post("/pubsub/order-ready")
    async def order_ready_push(request: Request) -> Response:
        return await _consume(request, order_ready)

    return app


async def _consume(request: Request, handler: Handler) -> Response:
    try:
        payload, _ = decode_push(await request.json())
    except ValueError as exc:  # Not JSON, or not a push envelope (InvalidPushMessage).
        logger.error("dropping malformed push request", extra={"error": str(exc)})
        return Response(status_code=204)
    try:
        await handler(payload)
    except PermanentError as exc:
        logger.error("dropping message after permanent error", extra={"error": str(exc)})
        return Response(status_code=204)
    except TransientError as exc:
        logger.warning("transient error; Pub/Sub will retry", extra={"error": str(exc)})
        return Response(status_code=503)
    except Exception:
        logger.exception("unexpected error; Pub/Sub will retry")
        return Response(status_code=500)
    return Response(status_code=204)
