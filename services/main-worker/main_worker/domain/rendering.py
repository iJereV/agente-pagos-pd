"""Text in and out of the agent: turn inputs, the sign-in placeholder, storage paths."""

import json
import mimetypes
from typing import Any
from urllib.parse import quote

from main_worker.domain.models import CustomerMessage

SIGN_IN_PLACEHOLDER = "{{SIGN_IN_LINK}}"

# Fixed customer-facing texts used when the agent turn fails or writes nothing.
TURN_FALLBACK_REPLY = "Perdón, tuve un problema para responderte. Probá de nuevo en un ratito."
ORDER_READY_FALLBACK_CAPTION = "¡Listo! Acá tenés tus imágenes."

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


def customer_turn_input(message: CustomerMessage) -> str:
    """The customer's text as-is; media is announced, followed by any caption."""
    if message.message_type == "text":
        return message.text or ""
    announcement = {
        "image": "[image received]",
        "document": "[document received]",
    }.get(message.message_type, "[unsupported message received]")
    return f"{announcement} {message.text}" if message.text else announcement


def system_event_input(event: str, **fields: Any) -> str:
    """A single ``SYSTEM_EVENT {...}`` line the agent recognises as a system event."""
    body = json.dumps({"event": event, **fields}, ensure_ascii=False, separators=(",", ":"))
    return f"SYSTEM_EVENT {body}"


def sign_in_url(link_web_url: str, token: str) -> str:
    return f"{link_web_url.rstrip('/')}/link?t={quote(token, safe='')}"


def render_sign_in_link(reply: str, url: str) -> str:
    """Replace the placeholder with the link, or append the link when it is missing."""
    if SIGN_IN_PLACEHOLDER in reply:
        return reply.replace(SIGN_IN_PLACEHOLDER, url)
    return f"{reply.rstrip()}\n\n{url}" if reply.strip() else url


def strip_sign_in_placeholder(reply: str) -> str:
    """Remove a placeholder the agent wrote without requesting a sign-in."""
    return reply.replace(SIGN_IN_PLACEHOLDER, "").strip()


def receipt_path(owner_id: str, wamid: str, mime_type: str) -> str:
    """``receipts/{customer_id or wa_id}/{wamid}.{ext}``."""
    return f"receipts/{owner_id}/{wamid}.{file_extension(mime_type)}"


def file_extension(mime_type: str) -> str:
    base = mime_type.split(";")[0].strip().lower()
    if base in _EXTENSIONS:
        return _EXTENSIONS[base]
    guessed = mimetypes.guess_extension(base)
    return guessed.lstrip(".") if guessed else "bin"


def content_type_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
