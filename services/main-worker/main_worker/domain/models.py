"""Inbound events and the records main-worker keeps in the ``channel`` database."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self

from main_worker.domain.errors import PermanentError

MEDIA_MESSAGE_TYPES = frozenset({"image", "document"})


@dataclass(frozen=True)
class CustomerMessage:
    wamid: str
    wa_id: str
    message_type: str
    text: str | None = None
    media_id: str | None = None
    mime_type: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        return cls(
            wamid=_required(payload, "wamid"),
            wa_id=_required(payload, "wa_id"),
            message_type=payload.get("message_type") or "other",
            text=payload.get("text"),
            media_id=payload.get("media_id"),
            mime_type=payload.get("mime_type"),
        )

    @property
    def has_media(self) -> bool:
        return self.message_type in MEDIA_MESSAGE_TYPES and bool(self.media_id)


@dataclass(frozen=True)
class SystemEvent:
    event: str
    event_id: str
    wa_id: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        return cls(
            event=_required(payload, "event"),
            event_id=_required(payload, "event_id"),
            wa_id=_required(payload, "wa_id"),
            data=dict(payload.get("data") or {}),
        )


@dataclass(frozen=True)
class OrderReady:
    order_id: str
    wa_id: str
    customer_id: str | None
    images: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        images = payload.get("images")
        if not isinstance(images, list) or not images:
            raise PermanentError("order_ready needs a non-empty images list")
        return cls(
            order_id=_required(payload, "order_id"),
            wa_id=_required(payload, "wa_id"),
            customer_id=payload.get("customer_id"),
            images=tuple(images),
        )


@dataclass(frozen=True)
class Identity:
    """Who is on the other side of a ``wa_id``, as main-worker resolved it."""

    wa_id: str
    customer_id: str | None
    auth_fresh: bool

    @property
    def is_linked(self) -> bool:
        return self.customer_id is not None


@dataclass(frozen=True)
class SessionPointer:
    """``channel/wa_sessions/{wa_id}``."""

    session_id: str
    last_activity: datetime
    last_inbound_at: datetime | None = None
    last_receipt_ref: str | None = None


@dataclass(frozen=True)
class MediaFile:
    data: bytes
    mime_type: str


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PermanentError(f"payload field {key!r} is missing")
    return value
