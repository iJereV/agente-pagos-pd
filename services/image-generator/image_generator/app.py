"""HTTP driving adapter: Pub/Sub push endpoint for `order-created`."""

import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from .models import OrderCreated
from .service import OrderImageService

logger = logging.getLogger(__name__)

PushDecoder = Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, str]]]


def create_app(service: OrderImageService, decode_push: PushDecoder) -> FastAPI:
    app = FastAPI(title="image-generator", docs_url=None, redoc_url=None)

    @app.post("/pubsub/order-created")
    def order_created(envelope: Annotated[dict[str, Any], Body()]) -> dict[str, str]:
        # A malformed event never becomes valid: answer 400 so Pub/Sub dead-letters it.
        try:
            payload, _attributes = decode_push(envelope)
            order = OrderCreated.model_validate(payload)
        except (ValueError, KeyError, TypeError) as error:
            detail = (
                error.errors(include_input=False)
                if isinstance(error, ValidationError)
                else str(error)
            )
            logger.error("invalid order_created event", extra={"detail": detail})
            raise HTTPException(status_code=400, detail="invalid order_created event") from error

        outcome = service.handle(order)
        return {"status": outcome.value}

    return app
