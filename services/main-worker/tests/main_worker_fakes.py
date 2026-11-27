"""In-memory implementations of the main-worker ports."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from main_worker.domain.errors import SessionNotFound
from main_worker.domain.models import MediaFile, OrderReady, SessionPointer


@dataclass
class FakeChannelStore:
    processed: dict[str, datetime] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    sign_ins: dict[str, datetime] = field(default_factory=dict)
    sessions: dict[str, SessionPointer] = field(default_factory=dict)
    link_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    deliveries: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def claim_message(self, message_id: str, now: datetime) -> bool:
        if message_id in self.processed:
            return False
        self.processed[message_id] = now
        return True

    async def release_message(self, message_id: str) -> None:
        self.processed.pop(message_id, None)

    async def linked_customer(self, wa_id: str) -> str | None:
        return self.links.get(wa_id)

    async def last_sign_in(self, customer_id: str) -> datetime | None:
        return self.sign_ins.get(customer_id)

    async def session_pointer(self, wa_id: str) -> SessionPointer | None:
        return self.sessions.get(wa_id)

    async def save_session_pointer(self, wa_id: str, pointer: SessionPointer) -> None:
        self.sessions[wa_id] = pointer

    async def save_link_token(
        self, token_hash: str, *, wa_id: str, purpose: str, expires_at: datetime
    ) -> None:
        self.link_tokens[token_hash] = {
            "wa_id": wa_id,
            "purpose": purpose,
            "expires_at": expires_at,
        }

    async def delivery_status(self, order_id: str) -> str | None:
        return self.deliveries.get(order_id, {}).get("status")

    async def mark_delivered(self, order: OrderReady, now: datetime) -> None:
        self.deliveries[order.order_id] = {
            "status": "delivered",
            "order": order,
            "delivered_at": now,
        }

    async def mark_awaiting_window(self, order: OrderReady) -> None:
        self.deliveries[order.order_id] = {"status": "awaiting_window", "order": order}

    async def awaiting_deliveries(self, wa_id: str) -> list[OrderReady]:
        return [
            d["order"]
            for d in self.deliveries.values()
            if d["status"] == "awaiting_window" and d["order"].wa_id == wa_id
        ]


@dataclass
class FakeMediaStore:
    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        self.objects[path] = (data, content_type)

    async def get(self, path: str) -> bytes:
        return self.objects[path][0]


@dataclass
class FakeWhatsApp:
    sent: list[tuple[str, str, Any]] = field(default_factory=list)
    media: dict[str, MediaFile] = field(default_factory=dict)
    uploads: list[tuple[str, bytes]] = field(default_factory=list)

    async def send_text(self, to: str, body: str) -> None:
        self.sent.append(("text", to, body))

    async def send_link_button(self, to: str, body: str, label: str, url: str) -> None:
        self.sent.append(("button", to, (body, label, url)))

    async def send_image(self, to: str, media_id: str) -> None:
        self.sent.append(("image", to, media_id))

    async def send_template(self, to: str, name: str, language: str) -> None:
        self.sent.append(("template", to, (name, language)))

    async def upload_media(self, data: bytes, mime_type: str, filename: str) -> str:
        self.uploads.append((filename, data))
        return f"uploaded-{len(self.uploads)}"

    async def download_media(self, media_id: str) -> MediaFile:
        return self.media[media_id]

    def buttons(self) -> list[tuple[str, str, str]]:
        return [payload for kind, _, payload in self.sent if kind == "button"]

    def texts(self) -> list[str]:
        return [body for kind, _, body in self.sent if kind == "text"]


@dataclass
class FakeAgentRuntime:
    """Replies with a scripted text; a reply may request a sign-in like the real agent."""

    replies: list[str] = field(default_factory=list)
    request_sign_in: bool = False
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    turns: list[tuple[str, str]] = field(default_factory=list)
    state_at_turn: list[dict[str, Any]] = field(default_factory=list)

    async def create_session(self, user_id: str, state: dict[str, Any]) -> str:
        session_id = f"session-{len(self.sessions) + 1}"
        self.sessions[session_id] = dict(state)
        return session_id

    async def update_state(self, user_id: str, session_id: str, delta: dict[str, Any]) -> None:
        if session_id not in self.sessions:
            raise SessionNotFound(session_id)
        self.sessions[session_id].update(delta)

    async def get_state(self, user_id: str, session_id: str) -> dict[str, Any]:
        return dict(self.sessions[session_id])

    async def run_turn(self, user_id: str, session_id: str, message: str) -> str:
        self.turns.append((session_id, message))
        self.state_at_turn.append(dict(self.sessions[session_id]))
        if self.request_sign_in:
            self.sessions[session_id]["sign_in_requested"] = True
        return self.replies.pop(0) if self.replies else "ok"
