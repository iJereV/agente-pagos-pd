"""Composition root wiring the Google Cloud adapters.

Served by `uvicorn image_generator.main:app`.
"""

import os
import random

from google import genai
from google.cloud import storage
from google.genai import types
from shared.pubsub import decode_push

from .adapters.gcs_store import GcsMediaStore
from .adapters.gemini_image import GeminiImageModel
from .adapters.pubsub_publisher import PubSubPublisher
from .app import create_app
from .logging_setup import configure_logging
from .service import OrderImageService

configure_logging()

_service = OrderImageService(
    image_model=GeminiImageModel(
        # The client is bound to where the image model is served (the global endpoint),
        # which is independent of the region the service runs in.
        genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("IMAGE_MODEL_LOCATION", "global"),
            # Free-trial billing accounts get intermittent 403s from Gemini
            # ("eligible paid billing account"); retry those with the usual codes.
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=6,
                    initial_delay=1.0,
                    max_delay=8.0,
                    http_status_codes=[403, 408, 429, 500, 502, 503, 504],
                )
            ),
        ),
        os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-lite-image"),
    ),
    store=GcsMediaStore(storage.Client(), os.environ["MEDIA_BUCKET"]),
    publisher=PubSubPublisher(os.environ["ORDER_READY_TOPIC"]),
    daily_cap=int(os.environ.get("DAILY_GENERATION_CAP", "200")),
    rng=random.SystemRandom(),
)

app = create_app(_service, decode_push)
