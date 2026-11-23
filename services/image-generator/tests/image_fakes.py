import base64
import copy
import json
from datetime import UTC, datetime
from typing import Any

NOW = datetime(2026, 11, 23, 15, 15, 2, tzinfo=UTC)


def order_payload(**overrides: Any) -> dict[str, Any]:
    """Synthetic `order_created` payload."""
    payload = {
        "type": "order_created",
        "order_id": "ord_TEST001",
        "customer_id": "uid-synthetic-1",
        "wa_id": "5490000000001",
        "items": [{"animal": "dog", "qty": 2}, {"animal": "capybara", "qty": 1}],
        "created_at": "2026-11-23T15:14:10Z",
    }
    return payload | overrides


class FakeImageModel:
    name = "fake-image-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_png(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return b"\x89PNG fake " + str(len(self.prompts)).encode()


class FakeMediaStore:
    """In-memory store with GCS-like generations."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[Any, int]] = {}
        self._next_generation = 1

    def _put(self, path: str, value: Any) -> None:
        self.objects[path] = (value, self._next_generation)
        self._next_generation += 1

    def read_json(self, path: str) -> dict[str, Any] | None:
        stored = self.objects.get(path)
        return None if stored is None else copy.deepcopy(stored[0])

    def read_json_versioned(self, path: str) -> tuple[dict[str, Any] | None, int]:
        stored = self.objects.get(path)
        return (None, 0) if stored is None else (copy.deepcopy(stored[0]), stored[1])

    def write_json(self, path: str, data: dict[str, Any]) -> None:
        self._put(path, copy.deepcopy(data))

    def write_json_if_generation(self, path: str, data: dict[str, Any], generation: int) -> bool:
        current = self.objects.get(path, (None, 0))[1]
        if current != generation:
            return False
        self._put(path, copy.deepcopy(data))
        return True

    def write_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self._put(path, data)


class RacingMediaStore(FakeMediaStore):
    """Simulates another instance bumping the counter between our read and write."""

    def __init__(self, races: int) -> None:
        super().__init__()
        self._races = races

    def write_json_if_generation(self, path: str, data: dict[str, Any], generation: int) -> bool:
        if self._races > 0:
            self._races -= 1
            current = self.read_json(path) or {"images": 0}
            super().write_json(path, {"images": current["images"] + 1})
        return super().write_json_if_generation(path, data, generation)


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, payload: dict[str, Any]) -> None:
        self.published.append(payload)


def push_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {
        "message": {
            "data": data,
            "attributes": {"type": payload.get("type", "")},
            "messageId": "1",
        },
        "subscription": "projects/demo/subscriptions/order-created-push",
    }
