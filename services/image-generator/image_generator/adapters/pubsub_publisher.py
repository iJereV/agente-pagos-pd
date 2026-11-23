"""EventPublisher backed by `shared.pubsub.publish_json`."""

from typing import Any

from shared.pubsub import publish_json


class PubSubPublisher:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def publish(self, payload: dict[str, Any]) -> None:
        publish_json(self._topic, payload)
