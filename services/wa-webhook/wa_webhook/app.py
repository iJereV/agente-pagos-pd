"""HTTP layer: Meta verification handshake and signed message notifications."""

import hmac
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from wa_webhook.messages import extract_customer_messages
from wa_webhook.signature import is_valid_signature

logger = logging.getLogger(__name__)

Publish = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class Settings:
    app_secret: str
    verify_token: str


def create_app(settings: Settings, publish: Publish) -> FastAPI:
    app = FastAPI(title="wa-webhook", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/webhook")
    def verify(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> Response:
        if mode == "subscribe" and hmac.compare_digest(token, settings.verify_token):
            return PlainTextResponse(challenge)
        return Response(status_code=403)

    @app.post("/webhook")
    async def receive(request: Request) -> Response:
        raw = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not is_valid_signature(raw, signature, settings.app_secret):
            logger.warning("rejected webhook with invalid signature")
            return Response(status_code=401)
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response(status_code=400)

        events = extract_customer_messages(payload)
        for event in events:
            # Blocking publish off the event loop; a failure returns 500 and Meta retries.
            await run_in_threadpool(publish, event)
        logger.info("enqueued webhook messages", extra={"count": len(events)})
        return Response(status_code=200)

    return app
