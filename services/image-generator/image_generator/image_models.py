"""Picks the ImageModel adapter from the model id.

``@cf/<publisher>/<model>`` runs on Cloudflare Workers AI (free daily allocation);
any other id is a Gemini image model on Vertex AI, which needs a paid billing account.
"""

import os

import httpx

from .ports import ImageModel

CLOUDFLARE_PREFIX = "@cf/"
# FLUX.1 [schnell] takes a few seconds; leave room for a slow response.
CLOUDFLARE_TIMEOUT_SECONDS = 60.0


def build_image_model(name: str) -> ImageModel:
    if name.startswith(CLOUDFLARE_PREFIX):
        from .adapters.cloudflare_image import CloudflareImageModel

        client = httpx.Client(
            timeout=CLOUDFLARE_TIMEOUT_SECONDS,
            headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
        )
        return CloudflareImageModel(client, os.environ["CLOUDFLARE_ACCOUNT_ID"], name)
    return _gemini(name)


def _gemini(name: str) -> ImageModel:
    from google import genai
    from google.genai import types

    from .adapters.gemini_image import GeminiImageModel

    # The client is bound to where the image model is served (the global endpoint),
    # which is independent of the region the service runs in.
    client = genai.Client(
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
    )
    return GeminiImageModel(client, name)
