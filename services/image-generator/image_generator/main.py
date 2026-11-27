"""Composition root wiring the adapters.

Served by `uvicorn image_generator.main:app`.
"""

import os
import random

from google.cloud import storage
from shared.pubsub import decode_push

from .adapters.gcs_store import GcsMediaStore
from .adapters.pubsub_publisher import PubSubPublisher
from .app import create_app
from .image_models import build_image_model
from .logging_setup import configure_logging
from .service import OrderImageService

configure_logging()

_service = OrderImageService(
    image_model=build_image_model(
        os.environ.get("IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    ),
    store=GcsMediaStore(storage.Client(), os.environ["MEDIA_BUCKET"]),
    publisher=PubSubPublisher(os.environ["ORDER_READY_TOPIC"]),
    daily_cap=int(os.environ.get("DAILY_GENERATION_CAP", "200")),
    rng=random.SystemRandom(),
)

app = create_app(_service, decode_push)
