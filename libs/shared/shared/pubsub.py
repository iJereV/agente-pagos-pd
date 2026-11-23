"""Pub/Sub helpers: decode push envelopes and publish JSON messages.

Every message carries a JSON object in ``data`` and repeats the event type in the
``type`` attribute (see docs/contracts.md).
"""

import base64
import binascii
import json
import os
from functools import cache
from typing import Any

from google.cloud import pubsub_v1


class InvalidPushMessage(ValueError):
    """The push request body is not a valid Pub/Sub envelope with a JSON object."""


def decode_push(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Return ``(payload, attributes)`` from a Pub/Sub push request body."""
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict) or "data" not in message:
        raise InvalidPushMessage("push body has no message.data")
    try:
        payload = json.loads(base64.b64decode(message["data"], validate=True))
    except (binascii.Error, ValueError, TypeError) as exc:
        raise InvalidPushMessage("message.data is not base64-encoded JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPushMessage("message.data must decode to a JSON object")
    attributes = message.get("attributes") or {}
    return payload, dict(attributes)


@cache
def _publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _topic_path(topic: str) -> str:
    if topic.startswith("projects/"):
        return topic
    return _publisher().topic_path(os.environ["GOOGLE_CLOUD_PROJECT"], topic)


def publish_json(topic: str, payload: dict[str, Any], **attributes: str) -> str:
    """Publish ``payload`` to ``topic`` (id or full path) and return the message id.

    The ``type`` attribute defaults to ``payload["type"]``.
    """
    attrs = {"type": str(payload.get("type", "")), **attributes}
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    future = _publisher().publish(_topic_path(topic), data, **attrs)
    return future.result(timeout=30)
