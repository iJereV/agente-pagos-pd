"""Driven ports. Adapters live in `image_generator.adapters`; tests use in-memory fakes."""

from typing import Any, Protocol


class ImageModel(Protocol):
    name: str

    def generate_png(self, prompt: str) -> bytes:
        """Returns one PNG image for the prompt. Raises on failure or empty output."""
        ...


class MediaStore(Protocol):
    def read_json(self, path: str) -> dict[str, Any] | None: ...

    def read_json_versioned(self, path: str) -> tuple[dict[str, Any] | None, int]:
        """Returns the document and its generation; generation 0 when it does not exist."""
        ...

    def write_json(self, path: str, data: dict[str, Any]) -> None: ...

    def write_json_if_generation(self, path: str, data: dict[str, Any], generation: int) -> bool:
        """Writes only if the stored generation still matches (0: must not exist)."""
        ...

    def write_bytes(self, path: str, data: bytes, content_type: str) -> None: ...


class EventPublisher(Protocol):
    def publish(self, payload: dict[str, Any]) -> None: ...
