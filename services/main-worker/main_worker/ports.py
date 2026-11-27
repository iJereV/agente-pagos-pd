"""Driven ports. Adapters in ``main_worker.adapters``; in-memory fakes in the tests."""

from datetime import datetime
from typing import Any, Protocol

from main_worker.domain.models import MediaFile, OrderReady, SessionPointer


class ChannelStore(Protocol):
    """The ``channel`` Firestore database."""

    async def claim_message(self, message_id: str, now: datetime) -> bool:
        """Create ``processed_messages/{id}``; False when it already exists."""

    async def release_message(self, message_id: str) -> None:
        """Forget a claim so a retried delivery is processed again."""

    async def linked_customer(self, wa_id: str) -> str | None: ...

    async def last_sign_in(self, customer_id: str) -> datetime | None: ...

    async def session_pointer(self, wa_id: str) -> SessionPointer | None: ...

    async def save_session_pointer(self, wa_id: str, pointer: SessionPointer) -> None: ...

    async def save_link_token(
        self, token_hash: str, *, wa_id: str, purpose: str, expires_at: datetime
    ) -> None: ...

    async def delivery_status(self, order_id: str) -> str | None: ...

    async def mark_delivered(self, order: OrderReady, now: datetime) -> None: ...

    async def mark_awaiting_window(self, order: OrderReady) -> None: ...

    async def awaiting_deliveries(self, wa_id: str) -> list[OrderReady]: ...


class MediaStore(Protocol):
    """The private media bucket."""

    async def put(self, path: str, data: bytes, content_type: str) -> None: ...

    async def get(self, path: str) -> bytes: ...


class WhatsApp(Protocol):
    """WhatsApp Cloud API, as the business phone number."""

    async def send_text(self, to: str, body: str) -> None: ...

    async def send_link_button(self, to: str, body: str, label: str, url: str) -> None:
        """``body`` with a call-to-action button labelled ``label`` that opens ``url``."""
        ...

    async def send_image(self, to: str, media_id: str) -> None: ...

    async def send_template(self, to: str, name: str, language: str) -> None: ...

    async def upload_media(self, data: bytes, mime_type: str, filename: str) -> str: ...

    async def download_media(self, media_id: str) -> MediaFile: ...


class AgentRuntime(Protocol):
    """Sessions and turns of the shop agent on Agent Runtime."""

    async def create_session(self, user_id: str, state: dict[str, Any]) -> str: ...

    async def update_state(self, user_id: str, session_id: str, delta: dict[str, Any]) -> None:
        """Raises ``SessionNotFound`` when the session no longer exists."""

    async def get_state(self, user_id: str, session_id: str) -> dict[str, Any]: ...

    async def run_turn(self, user_id: str, session_id: str, message: str) -> str:
        """Run one turn and return the agent's final plain-text reply."""
